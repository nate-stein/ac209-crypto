"""
Cryptocurrency data utils.

Used for preprocessing cryptocurrency and other data. `DesignMatrix` class
the main interface to producing features to feed into the machine learning
algorithms. Also contains scripts to scrape cryptocurrency data from
coinmarketcap.com.

Notes:
    Preprocessing of data that is for a cryptocurrency is different than for
    other assets. Therefore, the names of files containing data for
    cryptocurrency assets are hardcoded here and should be updated if new
    files are added to the data directory.

Earliest date data available for top 10 cryptocurrencies in terms of
market-cap on coinmarketcap.com as of April 1, 2018.
	eos: 07/01/2017
	xrp: 08/04/2013
	bch: 07/23/2017
	eth: 08/07/2015
	xlm: 08/05/2014
	neo: 09/09/2016
	miota: 06/13/2017
	btc: 04/28/2013
	ada: 10/01/2017
	ltc: 04/28/2013

Attributes:
    CRYPTO_NAMES (dict): Top 10 cryptocurrencies in terms of market
    capitalization as-of April 1, 2018 and corresponding shorthand names from
    coinmarketcap.com. The key values should be the strings used when
    scraping the data from the web-site.
    CRYPTO_SHORTHAND (dict): Reverse role of `CRYPTO_NAMES`. Converts
    shorthand code to full name.
"""
import copy
import datetime
import sys
import time
import warnings

import numpy as np
import pandas as pd
import sklearn.preprocessing as preprocessing

warnings.simplefilter(action='ignore', category=FutureWarning)

_MAX_UPDATE_LENGTH = 0  # used in method `print_update()`

CRYPTO_NAMES = {'ripple':'xrp', 'bitcoin':'btc', 'ethereum':'eth',
                'litecoin':'ltc', 'bitcoin-cash':'bch', 'eos':'eos',
                'cardano':'ada', 'stellar':'xlm', 'neo':'neo', 'iota':'miota'}
#
CRYPTO_SHORTHAND = {'xrp':'ripple', 'btc':'bitcoin', 'eth':'ethereum',
                    'ltc':'litecoin', 'bch':'bitcoin-cash', 'eos':'eos',
                    'ada':'cardano', 'xlm':'stellar', 'neo':'neo',
                    'miota':'iota'}

# Store earliest date for which data exists for cryptocurrencies passed to
# `_load_crypto_df()` function.
crypto_min_dates = {}


def file_name_corresponds_to_crypto (fname):
    if fname in CRYPTO_NAMES or fname in CRYPTO_SHORTHAND:
        return True
    return False


def _scrape_crypto (crypto, start_date=None, last_date=None):
    """Load and clean cryptocurrency data as time series from
    coinmarketcap.com.
    """
    # Load data from web-site.
    if start_date is None:
        start_date = pd.to_datetime('1/1/2011')
    # Convert to full name used by URL if given short code.
    if crypto in CRYPTO_SHORTHAND:
        crypto = CRYPTO_SHORTHAND[crypto]
    url = "https://coinmarketcap.com/currencies/{0}/historical-data/?start=" \
          "{1}&end={2}".format(crypto, start_date.strftime("%Y%m%d"),
                               time.strftime("%Y%m%d"))
    df = pd.read_html(url)[0]
    # Clean data / ensure proper dtypes.
    df['Date'] = pd.to_datetime(df['Date'])
    # Store minimum date in `crypto_min_dates` by short code.
    if crypto in CRYPTO_NAMES:
        crypto_min_dates[CRYPTO_NAMES[crypto]] = df['Date'].min()
    else:
        crypto_min_dates[crypto] = df['Date'].min()
    try:
        # Will throw "invalid type comparison" if the volume data is
        # already properly cast.
        df.loc[df['Volume']=='-', 'Volume'] = 0
    except TypeError:
        pass
    df['Volume'] = df['Volume'].astype('int64')
    # Rename columns.
    col_conversion = {'Date':'date', 'Open':'open', 'High':'high',
                      'Low':'low', 'Close':'close', 'Volume':'volume',
                      'Market Cap':'mkt_cap'}
    df.rename(columns=col_conversion, inplace=True)
    if last_date is not None:
        df = df[df['date']<=last_date]
    df.set_index('date', drop=True, inplace=True)
    return df


def scrape_crypto (crypto, start_date=None, end_date=None):
    """Returns cryptocurrency data time series."""
    if isinstance(crypto, str):
        # Single currency.
        return _scrape_crypto(crypto, start_date, end_date)

    # Multiple currencies.
    results = []
    for c in crypto:
        df = _scrape_crypto(c, start_date, end_date)
        results.append(df)
    return tuple(results)


def load_asset (fname):
    """Reads DataFrame from csv file from data folder as Time Series."""
    filepath = 'data/{}.csv'.format(fname)
    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', drop=True, inplace=True)
    return df


class DesignMatrix(object):
    """Creates design matrix for cryptocurrency algorithms.

    Args:
        x_cryptos (list): Cryptocurrencies we want to use to build our
        feature matrix. `y_crypto` is automatically added to corresponding
        `x_cryptos` attribute since we want to use trailing data for the
        cryptocurrency we are trying to predict as well so it should not be
        included in this list (if it is, it's simply removed).
        y_crypto (str): Cryptocurrency whose price return (direction) we want
        to predict.

    Keyword Args:
        n_rolling_price (int): Optional, default 1. Days over which to compute
        rolling (trailing) price returns.
        n_rolling_volume (int): Optional, default 1. Days over which to compute
        rolling change in trading volume.
        n_std_window_noncrypto (int): Optional, default 30. Days over which
        to standardize price changes for non-cryptocurrency assets (i.e.,
        items in `x_assets`.
        start_date (datetime.datetime): Desired beginning of rolling returns
        data.
        end_date (datetime.datetime): Desired end of rolling returns data
        period.
        n_std_window (int): Number of trailing observations to use in
        standardizing price and volume changes.

    Attributes:
        _x_features (list): Used to keep track of which features we add that
        will ultimately be used directly in design matrix.
    """

    def __init__ (self, x_cryptos, y_crypto, **kwargs):
        if y_crypto in x_cryptos:
            x_cryptos.remove(y_crypto)
        self.x_cryptos = x_cryptos
        self.y_crypto = y_crypto
        self.xy_cryptos = copy.copy(x_cryptos)
        self.xy_cryptos.append(y_crypto)
        self.x_assets = kwargs.get('x_assets', [])
        self.n_rolling_price = kwargs.get('n_rolling_price', 1)
        self.n_rolling_volume = kwargs.get('n_rolling_volume', 1)
        self.n_std_window_noncrypto = kwargs.get('n_std_window_noncrypto', 30)
        self.n_std_window = kwargs.get('n_std_window', 10)
        self.add_news = kwargs.get('add_news', False)
        self.news = kwargs.get('news', None)
        self.n_std_window = kwargs.get('n_std_window', 20)
        self.start_date = kwargs.get('start_date', pd.to_datetime('1/1/2010'))
        self.end_date = kwargs.get('end_date', pd.to_datetime('today'))
        self.df_time_series = None
        self.df_final = None
        self._x_features = []
        self.done_loading_time_series = False
        self.done_std_price_and_volume = False

    def get_data (self, std=True, lag_indicator=False, y_category=False,
                  y_category_thresh=0.01, y_std=False):
        """Performs all necessary steps to return finalized X, Y data.

        Args:
            std (bool): Optional, default True. If False, then data is not
            normalized/standardized.
            lag_indicator (bool): Optional, default False. If True,
            then `lagged_others` column is created.
            y_category (bool): Optional, default False. If True, then Y data is
            converted to a categorical variable: Buy: +1, Sell -1, Neutral 0.
            y_category_thresh (float): Optional, default 0.01. Only relevant
            if `y_category==True`. Y values with absolute value <=
            `y_category_thresh` will be classified as Neutral (0).
            y_std (bool): Optional, default False. If True, then the
            continuous Y is set to the standardized version, which impacts
            both the regression and classification Y. Only matters when
            std==True.
        """
        self._load_time_series()
        # If we standardize, the column name used to create our shifted Y
        # will be different.
        if std:
            self._standardize_price_volume()
            if y_std:
                y_continuous_col = '{}_px_std'.format(self.y_crypto)
            else:
                y_continuous_col = self.y_crypto
        else:
            y_continuous_col = self.y_crypto
        if lag_indicator:
            self._add_relative_lag_indicator()

        if self.add_news:
            self._add_news_features()

        self.df_final['Y'] = self.df_final[y_continuous_col].shift(periods=-1)
        self.df_final.dropna(axis=0, how='any', inplace=True)
        if y_category:
            self.df_final['Y'] = self._categorize_Y(self.df_final['Y'],
                                                    y_category_thresh)

        X = self.df_final[self.x_feature_names]
        Y = self.df_final['Y']
        return X, Y

    def _add_news_features(self):
        self.df_final = self.df_final.merge(self.news, left_index=True, right_index=True)
        self._x_features += list(self.news.columns)


    def _add_relative_lag_indicator (self):
        """Add indicator variable `lagged_others` indicating whether the price
        return of the Y crypto was lower than that of all the X cryptos.

        Assumes standardized price change columns have already been added.
        """

        def crypto_return_was_worst (row, y_crypto, x_cryptos):
            """Returns True if rolling price change for our Y crypto was
            worse than that of the X cryptos.
            """
            lowest_x = row[x_cryptos].min()
            return row[y_crypto]<lowest_x

        x_cols, y_col = self._get_crypto_price_change_col_names()
        func = lambda x:crypto_return_was_worst(x, y_col, x_cols)
        self.df_final['lagged_others'] = self.df_final.apply(func, axis=1)
        self._x_features.append('lagged_others')

    def _get_crypto_price_change_col_names (self):
        """Returns (X_list, Y_value) tuple of column names for the standardized
        price changes of the X and Y cryptos.
        """
        # Prepare column names for standardized price changes of X cryptos.
        x_crypto_cols = []
        for cryp in self.x_cryptos:
            x_crypto_cols.append('{}_px_std'.format(cryp))
        # Prepare Y crypto column name.
        y_crypto_col = '{}_px_std'.format(self.y_crypto)
        # Return both
        return x_crypto_cols, y_crypto_col

    def _load_crypto_time_series (self, crypto):
        """Load time series for cryptocurrency containing volume and closing
        price.

        Assumes that NaN values for volume arise from the fact that the
        volume for certain days is listed as 0 and, for these instances,
        fills NaN values with 0.
        """
        df = load_asset(crypto)
        df = df[['close', 'volume']]
        # Rename columns so they can be attributed to specific cryptocurrency.
        col_price = crypto
        col_vol = '{}_volume'.format(crypto)
        new_cols = {'close':col_price, 'volume':col_vol}
        df.rename(columns=new_cols, inplace=True)
        # Compute rolling figures.
        df.sort_index(ascending=True, inplace=True)
        df[col_price] = df[col_price].pct_change(periods=self.n_rolling_price)
        df[col_vol] = df[col_vol].pct_change(periods=self.n_rolling_volume)
        df[col_vol].fillna(value=0, inplace=True)
        # Reset index.
        start_date = max(self.start_date, df.index.min())
        end_date = min(self.end_date, df.index.max())
        new_date_idx = pd.date_range(start_date, end_date)
        df = df.reindex(index=new_date_idx, fill_value=np.NaN)
        # Ensure that the number of rows with missing values is only equal to
        # the trailing price window (i.e., beginning of dataset for which we
        # cannot compute trailing figures) because cryptos trade every day
        # and we don't expect NaNs.
        df_na = df[df.isnull().any(axis=1)]
        na_row_count = df_na.shape[0] - self.n_rolling_price
        if na_row_count>0:
            sys.stderr.write('Encountered {} null values in time series for '
                             '{}'.format(na_row_count, crypto))
            print(df_na.head())
        return df

    def _load_noncrypto_time_series (self, asset):
        df = load_asset(asset)
        # Price column already equal to name of asset.
        col_price = asset
        # Compute rolling figures.
        df.sort_index(ascending=True, inplace=True)
        df[col_price] = df[col_price].pct_change(periods=self.n_rolling_price)
        # Reset index.
        start_date = max(self.start_date, df.index.min())
        end_date = min(self.end_date, df.index.max())
        new_date_idx = pd.date_range(start_date, end_date)
        df = df.reindex(index=new_date_idx, fill_value=np.NaN)
        # Forward-fill missing values.
        df = df.ffill()
        return df

    def _load_time_series (self):
        """Init DataFrame formed by combining time series for each asset."""
        if self.done_loading_time_series:
            return
            # Load individual DFs for each asset.
        dfs = []
        for crypto in self.xy_cryptos:
            df = self._load_crypto_time_series(crypto)
            dfs.append(df)
        for asset in self.x_assets:
            df = self._load_noncrypto_time_series(asset)
            dfs.append(df)
        # Join DFs based on date index.
        df_result = pd.concat(dfs, axis=1, join='inner')
        # Drop rows with any N/As and print warning if more than 10 rows
        # dropped.
        rows_before = len(df_result.index)
        df_result.dropna(axis=0, how='any', inplace=True)
        rows_dropped = rows_before - len(df_result.index)
        if rows_dropped>10:
            sys.stderr.write('Warning: More than 10 N/A rows dropped in '
                             '`load_time_series`.')
        self.df_time_series = df_result
        self.df_final = df_result.copy(deep=True)
        self.done_loading_time_series = True

    @staticmethod
    def _categorize_Y (Y, threshold):
        new_Y = np.zeros(Y.shape[0], dtype=np.int16)
        for i, Y_i in enumerate(Y):
            if Y_i>threshold:
                new_Y[i] = 1
            elif Y_i<-threshold:
                new_Y[i] = -1
            else:
                new_Y[i] = 0
        return new_Y

    def _standardize_price_volume (self):
        """Add new columns containing standardized price and volume for all
        cryptocurrencies and standardized price for non-cryptocurrency assets.
        """
        if self.done_std_price_and_volume:
            return
        # Standardize cryptocurrency price and volume.
        n_cryp = self.n_std_window + 1
        for cryp in self.xy_cryptos:
            col_price = cryp
            col_vol = '{}_volume'.format(cryp)
            col_price_std = '{}_px_std'.format(cryp)
            col_vol_std = '{}_volume_std'.format(cryp)
            self._x_features.extend([col_price_std, col_vol_std])
            self.df_final[col_price_std] = self.df_final[col_price].rolling(
                  window=n_cryp).apply(rolling_standardize)
            self.df_final[col_vol_std] = self.df_final[col_vol].rolling(
                  window=n_cryp).apply(rolling_standardize)
        # Standardize non-cryptocurrency price.
        n_non_cryp = self.n_std_window_noncrypto + 1
        for x_asset in self.x_assets:
            col_price = x_asset
            col_price_std = '{}_px_std'.format(x_asset)
            self._x_features.append(col_price_std)
            self.df_final[col_price_std] = self.df_final[col_price].rolling(
                  window=n_non_cryp).apply(rolling_standardize)

        self.done_std_price_and_volume = True

    @property
    def x_feature_names (self):
        """Returns columns pertaining to design matrix."""
        x_feats = copy.copy(self._x_features)
        if not self.done_std_price_and_volume:
            for x in self.x_assets:
                x_feats.append(x)
        return x_feats


def rolling_standardize (x):
    """Intended to be used on pandas.core.window.Rolling.apply().

    It is assumed x is sorted in ascending time series order such that x[-1]
    is the most recent observation and x[:-1] is its trailing window.
    """
    x_current = x[-1]
    x_trailing = x[0:-1]
    return (x_current - np.mean(x_trailing))/np.std(x_trailing)


def load_returns_matrix (assets, xdays=None, start_date=None,
                         end_date=None, center=True, scale=True,
                         use_shortnames=True):
    """Returns design matrix.

    Notes:
        Different rolling returns methodologies are used for cryptocurrencies
        and non-cryptocurrency assets. For cryptocurrencies, there is a
        strict requirement that there be a price on t and t+1.

    Args:
        assets (list): Assets to include in returns matrix.
        xdays (int): Optional, defaults to 1 (daily). Rolling return
        frequency in terms of number of days.
    """
    # Determine the `freq` argument for pandas.DataFrame.pct_change().
    # Different args will be used for cryptos vs. non-cryptos.
    if xdays is None:
        xdays = 1
    elif not isinstance(xdays, int):
        raise ValueError('Optional `xdays` should be an int.')

    if start_date is None:
        start_date = pd.to_datetime('1/1/2010')
    if end_date is None:
        end_date = pd.to_datetime('today')

    # Create time series for each asset's closing price.
    dfs = []
    for asset in assets:
        is_crypto = file_name_corresponds_to_crypto(asset)
        df = load_asset(asset)
        if is_crypto:
            # Currently only crypto files contain data other than closing price.
            # Non-cryptos will already contain single column with name equal
            # to the asset name.
            df = df[['close']]
            df.rename(columns={'close':asset}, inplace=True)
        # Sort date index in descending order to ensure rolling calculations
        # are performed correctly.
        df.sort_index(ascending=True, inplace=True)
        df = df.pct_change(periods=xdays)
        # Create new index.
        start_date_i = max(start_date, df.index.min())
        end_date_i = max(end_date, df.index.max())
        date_idx = pd.date_range(start_date_i, end_date_i)
        df = df.reindex(index=date_idx, fill_value=np.NaN)
        df = df.ffill()
        dfs.append(df)

    # Join all the time series.
    dfout = pd.concat(dfs, axis=1, join='inner')

    # Filter to desired date range (if date restrictions provided).
    if start_date:
        dfout = dfout[dfout.index>=start_date]
    if end_date:
        dfout = dfout[dfout.index<=end_date]

    # Drop rows with any N/As and print warning if more than 10 rows
    # dropped.
    rows_before = len(dfout.index)
    dfout.dropna(axis=0, how='any', inplace=True)
    rows_dropped = rows_before - len(dfout.index)
    if rows_dropped>10:
        sys.stderr.write('Warning: More than 10 N/A rows dropped in '
                         'load_returns_matrix.')
    # Standardize data (if desired).
    if center or scale:
        xout = preprocessing.scale(dfout, axis=0, with_mean=center,
                                   with_std=scale)
        dfout = pd.DataFrame(xout, columns=dfout.columns, index=dfout.index)
    if use_shortnames:
        dfout.rename(columns=CRYPTO_NAMES, inplace=True)
    return dfout


def print_update (msg):
    """Handles writing updates to stdout when we want to clear previous
    outputs to the console (or other stdout).
    """
    global _MAX_UPDATE_LENGTH
    _MAX_UPDATE_LENGTH = max(_MAX_UPDATE_LENGTH, len(msg))
    empty_chars = _MAX_UPDATE_LENGTH - len(msg)
    msg = '{0}{1}'.format(msg, ' '*empty_chars)
    sys.stdout.write('{}\r'.format(msg))
    sys.stdout.flush()


def save_cryptos_to_file ():
    """Script used to save cryptocurrency data to CSVs."""
    for crypto in CRYPTO_SHORTHAND.keys():
        print_update('Saving {}'.format(crypto))
        df = scrape_crypto(crypto)
        save_path = 'data/{}.csv'.format(crypto)
        df.to_csv(save_path)


def fmt_date (dt):
    """Applies same date formatting for both Python's datetime and
    numpy.datetime64 objects.
    """
    if isinstance(dt, datetime.datetime):
        return dt.strftime("%m/%d/%Y")
    elif isinstance(dt, np.datetime64):
        return pd.to_datetime(str(dt)).strftime("%m/%d/%Y")
    else:
        raise ValueError('Unhandled type: {}'.format(type(dt)))


if __name__=='__main__':
    x_cryptos = ['ltc', 'xrp', 'xlm', 'eth']
    y_crypto = 'btc'
    params = {'n_rolling_price':1, 'n_rolling_volume':2,
              'x_assets':['SP500'], 'n_std_window':20}

    dm = DesignMatrix(x_cryptos=x_cryptos, y_crypto=y_crypto, **params)
    X, Y = dm.get_data(add_news=True)
    print(X.head(5))
