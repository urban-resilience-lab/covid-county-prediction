from covid_county_prediction.DataLoader import DataLoader
from torch.utils.data import Dataset
from datetime import timedelta
from covid_county_prediction.FeaturesList import FeaturesList
import covid_county_prediction.config.RawFeatureExtractorConfig as rfe_config
import covid_county_prediction.config.CovidCountyDatasetConfig as config
import covid_county_prediction.config.features_config as features_config
import covid_county_prediction.config.model_hyperparam_config as hyperparams
import bisect
import os
from tqdm import tqdm
import torch
from covid_county_prediction.utils import timed_logger_decorator
from math import ceil, floor


class CovidCountyDataset(DataLoader, Dataset):
    def __init__(self, data_start_date, data_end_date, means_stds,
                 use_cache=True):
        super(CovidCountyDataset, self).__init__()

        self.start_date = data_start_date
        self.end_date   = data_end_date
        self.use_cache  = use_cache
        self.is_cached  = False
        self.means_stds = means_stds

        self.cache = {}

        self._load_cache_from_disk()

        if self.is_cached:
            return

        self.labels_lens = []

        # load all labels
        d = self.start_date
        self.labels = []
        while d < self.end_date:
            cur_labels = self.load_num_cases(d, d + timedelta(days=1)).raw_features[0]
            cur_labels = cur_labels.dropna()

            cur_end = d - timedelta(hyperparams.projection_days)
            cur_start = cur_end - timedelta(hyperparams.past_days_to_consider)

            self.labels.append(
                (
                    cur_start,
                    cur_end,
                    cur_labels
                )
            )

            if self.labels_lens:
                self.labels_lens.append(
                    self.labels_lens[-1] + cur_labels.shape[0]
                )
            else:
                self.labels_lens.append(cur_labels.shape[0])
            d += timedelta(days=1)

        training_data_end_date = \
            self.end_date - timedelta(hyperparams.projection_days)

        training_data_start_date = \
            self.start_date - timedelta(hyperparams.projection_days) -\
            timedelta(hyperparams.past_days_to_consider)

        features = [
            self.load_census_data(),
            self.load_sg_patterns_monthly(training_data_start_date, training_data_end_date),
            # self.read_weather_data(training_data_start_date, training_data_end_date),
            self.load_sg_social_distancing(training_data_start_date, training_data_end_date),
            self.load_num_cases(training_data_start_date, training_data_end_date),
            self.load_sg_mobility_incoming(training_data_start_date, training_data_end_date),
            self.load_countywise_cumulative_cases(training_data_start_date, training_data_end_date)
        ]

        if means_stds is None:
            means_stds = [(None, None)] * len(features)

        assert len(means_stds) == len(features)

        self.means_stds = []

        for i in range(len(features)):
            self.means_stds.append(
                features[i].normalize(
                    mean=means_stds[i][0], std=means_stds[i][1]
                )
            )

        self.features = FeaturesList(features)

        assert len(self.features) == config.num_features

    def __len__(self):
        if self.is_cached:
            return len(self.cache)
        return self.labels_lens[-1]

    @timed_logger_decorator
    def _load_cache_from_disk(self):
        saved_cache_path = config.get_cached_tensors_path(
                                self.start_date, self.end_date
                            )

        if self.use_cache:
            if os.path.exists(saved_cache_path):
                self.cache = torch.load(saved_cache_path)
                self.is_cached = True
            else:
                raise Exception('use_cache is True but saved file is absent')

    def _classify_label(self, label):
        assert ceil(label) == floor(label) and label == label
        return bisect.bisect_left(config.labels_class_boundaries, label)

    def save_cache_on_disk(self):
        for i in tqdm(range(len(self))):
            self[i]  # results are automatically cached

        assert len(self.cache) == len(self)  # ensure cache is filled

        save_path = config.get_cached_tensors_path(
                        self.start_date, self.end_date
                    )
        with open(save_path, 'wb') as f:
            torch.save(self.cache, f)

    def __getitem__(self, idx):
        if idx in self.cache:
            return self.cache[idx]

        labels_idx = bisect.bisect_left(self.labels_lens, idx)
        if self.labels_lens[labels_idx] == idx:
            labels_idx += 1

        df_idx = idx - self.labels_lens[labels_idx]
        out = self.features.extract_torch_tensors(
                county_fips=self.labels[labels_idx][2].iloc[df_idx].name,
                start_date=self.labels[labels_idx][0],
                end_date=self.labels[labels_idx][1]
            )

        out[config.labels_key] = \
            self._classify_label(self.labels[labels_idx][2].values[df_idx, 0])

        if idx not in self.cache:
            self.cache[idx] = out

        return out
