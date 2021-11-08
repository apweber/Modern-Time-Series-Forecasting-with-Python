import numpy as np
from functools import partial
from src.decomposition.seasonal import _detrend

def make_stationary(x: np.ndarray, method: str="detrend", detrend_kwargs:dict={}):
    """Utility to make time series stationary

    Args:
        x (np.ndarray): The time series array to be made stationary
        method (str, optional): {"detrend","logdiff"}. Defaults to "detrend".
        detrend_kwargs (dict, optional): These kwargs will be passed on to the detrend method
    """
    if method=="detrend":
        detrend_kwargs["return_trend"] = True
        stationary, trend = _detrend(x, **detrend_kwargs)
        def inverse_transform(st, trend):
            return st+trend
        return stationary, partial(inverse_transform, trend=trend)
    elif method == "logdiff":
        stationary = np.log(x[:-1]/x[1:])
        def inverse_transform(st, x):
            _x = np.exp(st)
            return _x*x[1:]
        return stationary, partial(inverse_transform, x=x)

from darts import TimeSeries
from darts.metrics.metrics import _get_values_or_raise, _remove_nan_union, mae, mse, mase
from typing import Optional, Union, Sequence, Callable
from src.utils.data_utils import is_datetime_dtypes
import pandas as pd

def forecast_bias(actual_series: Union[TimeSeries, Sequence[TimeSeries], np.ndarray],
        pred_series: Union[TimeSeries, Sequence[TimeSeries], np.ndarray],
        intersect: bool = True,
        *,
        reduction: Callable[[np.ndarray], float] = np.mean,
        inter_reduction: Callable[[np.ndarray], Union[float, np.ndarray]] = lambda x: x,
        n_jobs: int = 1,
        verbose: bool = False) -> Union[float, np.ndarray]:
    """ Forecast Bias (FB).

    Given a time series of actual values :math:`y_t` and a time series of predicted values :math:`\\hat{y}_t`
    both of length :math:`T`, it is a percentage value computed as

    .. math:: 100 \\cdot \\frac{\\sum_{t=1}^{T}{y_t}
              - \\sum_{t=1}^{T}{\\hat{y}_t}}{\\sum_{t=1}^{T}{y_t}}.

    If any of the series is stochastic (containing several samples), the median sample value is considered.

    Parameters
    ----------
    actual_series
        The `TimeSeries` or `Sequence[TimeSeries]` of actual values.
    pred_series
        The `TimeSeries` or `Sequence[TimeSeries]` of predicted values.
    intersect
        For time series that are overlapping in time without having the same time index, setting `intersect=True`
        will consider the values only over their common time interval (intersection in time).
    reduction
        Function taking as input a `np.ndarray` and returning a scalar value. This function is used to aggregate
        the metrics of different components in case of multivariate `TimeSeries` instances.
    inter_reduction
        Function taking as input a `np.ndarray` and returning either a scalar value or a `np.ndarray`.
        This function can be used to aggregate the metrics of different series in case the metric is evaluated on a
        `Sequence[TimeSeries]`. Defaults to the identity function, which returns the pairwise metrics for each pair
        of `TimeSeries` received in input. Example: `inter_reduction=np.mean`, will return the average of the pairwise
        metrics.
    n_jobs
        The number of jobs to run in parallel. Parallel jobs are created only when a `Sequence[TimeSeries]` is
        passed as input, parallelising operations regarding different `TimeSeries`. Defaults to `1`
        (sequential). Setting the parameter to `-1` means using all the available processors.
    verbose
        Optionally, whether to print operations progress

    Raises
    ------
    ValueError
        If :math:`\\sum_{t=1}^{T}{y_t} = 0`.

    Returns
    -------
    float
        The Forecast Bias (OPE)
    """
    assert type(actual_series) is type(pred_series), "actual_series and pred_series should be of same type."
    if isinstance(actual_series, np.ndarray):
        y_true, y_pred = actual_series, pred_series
    else:
        y_true, y_pred = _get_values_or_raise(actual_series, pred_series, intersect)
    y_true, y_pred = _remove_nan_union(y_true, y_pred)
    y_true_sum, y_pred_sum = np.sum(y_true), np.sum(y_pred)
    # raise_if_not(y_true_sum > 0, 'The series of actual value cannot sum to zero when computing OPE.', logger)
    return ((y_true_sum - y_pred_sum) / y_true_sum) * 100.

def darts_metrics_adapter(metric_func, actual_series: Union[TimeSeries, Sequence[TimeSeries]],
        pred_series: Union[TimeSeries, Sequence[TimeSeries]],
        insample: Union[TimeSeries, Sequence[TimeSeries]] = None,
        m: Optional[int] = 1,
        intersect: bool = True,
        reduction: Callable[[np.ndarray], float] = np.mean,
        inter_reduction: Callable[[np.ndarray], Union[float, np.ndarray]] = lambda x: x,
        n_jobs: int = 1,
        verbose: bool = False):
    
    assert type(actual_series) is type(pred_series), "actual_series and pred_series should be of same type."
    if insample is not None:
        assert type(actual_series) is type(insample), "actual_series and insample should be of same type."
    is_nd_array = isinstance(actual_series, np.ndarray)
    is_pd_series = isinstance(actual_series, pd.Series)
    is_pd_dataframe = isinstance(actual_series, pd.DataFrame)
    if is_pd_dataframe and actual_series.shape[1]==1:
        actual_series = actual_series.squeeze()
        pred_series = pred_series.squeeze()
        if insample is not None:
            insample = insample.squeeze()
        is_pd_series = True
    else:
        raise ValueError("Dataframes not supported in the adapter. Use either Series with datetime index or numpy arrays")
    if is_pd_series:
        is_datetime_index = is_datetime_dtypes(actual_series.index) and is_datetime_dtypes(pred_series.index)
        if insample is not None:
            is_datetime_index = is_datetime_index and is_datetime_dtypes(insample.index)
    else:
        is_datetime_index = False
    if metric_func.__name__ == "mase":
        if not is_datetime_index:
            raise ValueError("MASE needs pandas Series with datetime index as inputs")
    
    if is_nd_array or (is_pd_series and not is_datetime_index):
        actual_series, pred_series = TimeSeries.from_values(actual_series.values if is_pd_series else actual_series), TimeSeries.from_values(pred_series.values if is_pd_series else pred_series)
        if insample is not None:
            insample = TimeSeries.from_values(insample.values if is_pd_series else insample)

    elif is_pd_series and is_datetime_index:
        actual_series, pred_series = TimeSeries.from_series(actual_series), TimeSeries.from_series(pred_series)
        if insample is not None:
            insample = TimeSeries.from_series(insample)
    else:
        raise ValueError()
    if metric_func.__name__ == "mase":
        return metric_func(actual_series=actual_series, pred_series=pred_series, insample=insample, m=m, intersect=intersect, reduction=reduction, inter_reduction=inter_reduction, n_jobs=n_jobs, verbose=verbose)
    else:
        return metric_func(actual_series=actual_series, pred_series=pred_series, intersect=intersect, reduction=reduction, inter_reduction=inter_reduction, n_jobs=n_jobs, verbose=verbose)
