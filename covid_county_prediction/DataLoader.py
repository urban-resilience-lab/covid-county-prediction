from covid_county_prediction.DataSaver import DataSaver
import covid_county_prediction.config.DataSaverConfig as saver_config
import os
import pandas as pd
from covid_county_prediction.ConstantFeatures import ConstantFeatures
from covid_county_prediction.CountyWiseTimeDependentFeatures import CountyWiseTimeDependentFeatures
from covid_county_prediction.TimeDependentFeatures import TimeDependentFeatures
from datetime import timedelta


class DataLoader(DataSaver):
    def __init__(self):
        super(DataLoader, self).__init__()

    def load_census_data(self):
        self._save_if_not_saved(
            saver_config.census_data_path,
            self.save_census_data
        )

        df = pd.read_csv(saver_config.census_data_path).set_index('fips')

        return ConstantFeatures(df, 'open_census_data')

    def load_sg_patterns_monthly(self, start_date, end_date):
        return self._load_time_dep_features(
            start_date, end_date, saver_config.get_sg_patterns_monthly_file,
            self.save_sg_patterns_monthly, TimeDependentFeatures,
            'monthly_patterns'
        )

    def load_sg_social_distancing(self, start_date, end_date):
        return self._load_time_dep_features(
            start_date, end_date, saver_config.get_sg_social_distancing_file,
            self.save_sg_social_distancing, TimeDependentFeatures,
            'social_distancing'
        )

    def load_weather_data(self, start_date, end_date):
        return self._load_time_dep_features(
            start_date, end_date, saver_config.get_weather_file,
            self.save_weather_data, TimeDependentFeatures,
            'weather_data'
        )

    def load_num_cases(self, start_date, end_date):
        return self._load_time_dep_features(
            start_date, end_date, saver_config.get_num_cases_file,
            self.save_num_cases, TimeDependentFeatures,
            'num_cases'
        )

    def load_countywise_cumulative_cases(self, start_date, end_date):
        return self._load_time_dep_features(
            start_date, end_date,
            saver_config.get_countywise_cumulative_cases_file,
            self.save_countywise_cumulative_cases,
            CountyWiseTimeDependentFeatures,
            'countywise_cumulative_cases'
        )

    def _load_time_dep_features(self, start_date, end_date, get_path, saver,
                                feature_type, feature_name,
                                interval=timedelta(1)):
        self._save_if_not_saved(get_path, saver, start_date, end_date)

        dfs = []
        cur_date = start_date
        while(cur_date < end_date):
            dfs.append(pd.read_csv(get_path(cur_date)).set_index('fips'))
            cur_date += interval

        return feature_type(dfs, feature_name, start_date, interval)

    def _save_if_not_saved(self, saved_path_or_get_path, saver,
                           start_date=None, end_date=None):
        if isinstance(saved_path_or_get_path, str):
            if not os.path.exists(saved_path_or_get_path):
                if start_date is None and end_date is None:
                    saver()
                elif start_date is not None and end_date is not None:
                    saver(start_date, end_date)
                else:
                    raise Exception('either both start_date, end_date must be'
                                    'provided or none must be')
        else:  # saved_path_or_get_path is a function
            cur_date = start_date
            while cur_date < end_date:
                if not os.path.exists(saved_path_or_get_path(cur_date)):
                    saver(cur_date, end_date)
                cur_date += timedelta(1)