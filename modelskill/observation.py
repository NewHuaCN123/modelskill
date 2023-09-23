"""
The `observation` module contains different types of Observation classes for
fixed locations (PointObservation), or locations moving in space (TrackObservation).

Examples
--------
>>> o1 = PointObservation("klagshamn.dfs0", item=0, x=366844, y=6154291, name="Klagshamn")
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
import xarray as xr
import mikeio
from copy import deepcopy

from .utils import _get_name, make_unique_index
from .types import Quantity
from .timeseries import TimeSeries


# def _parse_item(items, item, item_str="item"):
#     if isinstance(item, int):
#         item = len(items) + item if (item < 0) else item
#         if (item < 0) or (item >= len(items)):
#             raise IndexError(f"{item_str} is out of range (0, {len(items)})")
#     elif isinstance(item, str):
#         item = items.index(item)
#     else:
#         raise TypeError(f"{item_str} must be int or string")
#     return item


def _get_item_names(items, valid_names):
    if len(valid_names) < len(items):
        raise ValueError(
            f"Input has only {len(valid_names)} items. {len(items)} items where requested: {items}"
        )

    # more valid_names than items and at least one item is None
    if len(valid_names) > len(items) and any([i is None for i in items]):
        raise ValueError(
            f"Cannot infer item names from input. Please provide item names explicitly. Valid names: {valid_names}."
        )
    item_names = []
    for item in items:
        item_names.append(_get_name(x=item, valid_names=valid_names))
    if len(item_names) != len(set(item_names)):
        raise ValueError("Items must be unique")
    return item_names


class Observation(TimeSeries):
    """Base class for observations

    Parameters
    ----------
    data : pd.DataFrame
    name : str, optional
        user-defined name, e.g. "Station A", by default "Observation"
    quantity : Optional[Quantity], optional
        The quantity of the observation, for validation with model results
    weight : float, optional
        weighting factor, to be used in weighted skill scores, by default 1.0
    color : str, optional
        color of the observation in plots, by default "#d62728"
    """

    def __init__(
        self,
        data: xr.Dataset,
        name: Optional[str] = None,
        quantity: Optional[Quantity] = None,
        weight: float = 1.0,
        color: str = "#d62728",
    ):
        # TODO: now handles both xr and pandas
        # time = data.index if hasattr(data, "index") else data.time
        # time = self._parse_time(time)
        # if hasattr(data, "index"):
        #     data.index = time
        # else:
        #     data["time"] = time
        data["time"] = self._parse_time(data.time)

        if quantity is None:
            quantity = Quantity.undefined()

        if name is None:
            name = "Observation"

        self.weight = weight

        super().__init__(name=name, data=data, quantity=quantity, color=color)

    @staticmethod
    def _parse_time(time):
        # TODO move this to TimeSeries?

        if isinstance(time, pd.DatetimeIndex):
            time = time.round(freq="100us")  # 0.0001s accuracy
            return pd.DatetimeIndex(time, freq="infer")
        else:
            if not isinstance(time.to_index(), pd.DatetimeIndex):
                raise TypeError(
                    f"Input must have a datetime index! Provided index was {type(time)}"
                )
            return time.dt.round("100us")

    @property
    def values(self) -> np.ndarray:
        """Observed values"""
        return self.data.to_pandas().values

    @property
    def n_points(self):
        """Number of observation points"""
        return len(self.data.time)

    def copy(self):
        return deepcopy(self)


class PointObservation(Observation):
    """Class for observations of fixed locations

    Create a PointObservation from a dfs0 file or a pd.DataFrame.

    Parameters
    ----------
    data : (str, Path, mikeio.Dataset, mikeio.DataArray, pd.DataFrame, pd.Series, xr.Dataset, xr.DataArray)
        filename or object with the data
    item : (int, str), optional
        index or name of the wanted item/column, by default None
        if data contains more than one item, item must be given
    x : float, optional
        x-coordinate of the observation point, by default None
    y : float, optional
        y-coordinate of the observation point, by default None
    z : float, optional
        z-coordinate of the observation point, by default None
    name : str, optional
        user-defined name for easy identification in plots etc, by default file basename
    quantity : Quantity, optional
        The quantity of the observation, for validation with model results

    Examples
    --------
    >>> o1 = PointObservation("klagshamn.dfs0", item=0, x=366844, y=6154291, name="Klagshamn")
    >>> o1 = PointObservation("klagshamn.dfs0", item="Water Level", x=366844, y=6154291)
    >>> o1 = PointObservation(df, item=0, x=366844, y=6154291, name="Klagshamn")
    >>> o1 = PointObservation(df["Water Level"], x=366844, y=6154291)
    """

    @property
    def geometry(self):
        from shapely.geometry import Point

        if self.z is None:
            return Point(self.x, self.y)
        else:
            return Point(self.x, self.y, self.z)

    def __init__(
        self,
        data,
        *,
        item: Optional[int | str] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        name: Optional[str] = None,
        quantity: Optional[Quantity] = None,
    ):
        self.x = x
        self.y = y
        self.z = z

        self._filename = None
        self._item = None

        if isinstance(data, (str, Path)):
            assert (
                Path(data).suffix == ".dfs0"
            ), "File must be a dfs0 file, other file types must be read with pandas or xarray"
            name = name or Path(data).stem
            data = mikeio.read(data)  # now mikeio.Dataset
        elif isinstance(data, mikeio.Dfs0):
            data = data.read()  # now mikeio.Dataset

        # parse item and convert to xr.Dataset
        if isinstance(data, (mikeio.Dataset, mikeio.DataArray)):
            ds, item_name = self._mikeio_dataset(data, item)
            iteminfo = ds[item_name].item
            ds = ds.to_xarray()
            if quantity is None:
                quantity = Quantity.from_mikeio_iteminfo(iteminfo)

        elif isinstance(data, (pd.DataFrame, pd.Series)):
            ds, item_name = self._pandas_to_xarray(data, item)
        elif isinstance(data, (xr.Dataset, xr.DataArray)):
            ds, item_name = self._xarray_to_xarrray(data, item)
        else:
            raise TypeError(
                f"input must be str, Path, mikeio.DataArray/Dataset, pd.Series/DataFrame or xr.Dataset/DataArray! Given input has type {type(data)}"
            )

        if not ds.time.to_index().is_monotonic_increasing:
            # TODO: duplicates_keep="mean","first","last"
            raise ValueError(
                "Time axis has duplicate entries. It must be monotonically increasing."
            )

        ds = ds.dropna(dim="time")

        super().__init__(
            name=name,
            data=ds,
            quantity=quantity,
        )

    def _mikeio_dataset(self, data, item):
        assert len(data.shape) == 1, "Only 0-dimensional data are supported"
        if isinstance(data, mikeio.Dataset):
            item_names = [i.name for i in data.items]
            item_name = _get_name(x=item, valid_names=item_names)
            ds = data[[item_name]]
        elif isinstance(data, mikeio.DataArray):
            if item is not None:
                raise ValueError("item must be None when data is a mikeio.DataArray")
            item_name = data.name
            ds = data._to_dataset()

        return ds, item_name

    def _pandas_to_xarray(self, data, item):
        if isinstance(data, pd.DataFrame):
            item_name = _get_name(x=item, valid_names=list(data.columns))
            df = data[[item_name]]
        else:
            if item is not None:
                raise ValueError("item must be None when data is a pd.Series")
            df = pd.DataFrame(data)  # to_frame?
            item_name = df.columns[0]
        df.index.name = "time"
        return df.to_xarray(), item_name

    def _xarray_to_xarrray(self, data, item):
        if isinstance(data, xr.Dataset):
            item_name = _get_name(x=item, valid_names=list(data.data_vars))
            ds = data[[item_name]]
        else:
            if item is not None:
                raise ValueError("item must be None when data is a xr.DataArray")
            item_name = data.name
            ds = data.to_dataset()

        assert len(ds.dims) == 1, "Only 0-dimensional data are supported"

        # check that name of coords is "time", rename if not
        if ds.coords[list(ds.coords)[0]].name != "time":
            ds = ds.rename({list(ds.coords)[0]: "time"})

        return ds, item_name

    def __repr__(self):
        out = f"PointObservation: {self.name}, x={self.x}, y={self.y}"
        return out


class TrackObservation(Observation):
    """Class for observation with locations moving in space, e.g. satellite altimetry

    The data needs in addition to the datetime of each single observation point also, x and y coordinates.

    Create TrackObservation from dfs0 or DataFrame

    Parameters
    ----------
    data : (str, Path, mikeio.Dataset, pd.DataFrame, xr.Dataset)
        path to dfs0 file or object with track data
    item : (str, int), optional
        item name or index of values, by default None
        if data contains more than one item, item must be given
    name : str, optional
        user-defined name for easy identification in plots etc, by default file basename
    x_item : (str, int), optional
        item name or index of x-coordinate, by default 0
    y_item : (str, int), optional
        item name or index of y-coordinate, by default 1
    offset_duplicates : float, optional
        in case of duplicate timestamps, add this many seconds to consecutive duplicate entries, by default 0.001


    Examples
    --------
    >>> o1 = TrackObservation("track.dfs0", item=2, name="c2")

    >>> o1 = TrackObservation("track.dfs0", item="wind_speed", name="c2")

    >>> o1 = TrackObservation("lon_after_lat.dfs0", item="wl", x_item=1, y_item=0)

    >>> o1 = TrackObservation("track_wl.dfs0", item="wl", x_item="lon", y_item="lat")

    >>> df = pd.DataFrame(
    ...         {
    ...             "t": pd.date_range("2010-01-01", freq="10s", periods=n),
    ...             "x": np.linspace(0, 10, n),
    ...             "y": np.linspace(45000, 45100, n),
    ...             "swh": [0.1, 0.3, 0.4, 0.5, 0.3],
    ...         }
    ... )
    >>> df = df.set_index("t")
    >>> df
                        x        y  swh
    t
    2010-01-01 00:00:00   0.0  45000.0  0.1
    2010-01-01 00:00:10   2.5  45025.0  0.3
    2010-01-01 00:00:20   5.0  45050.0  0.4
    2010-01-01 00:00:30   7.5  45075.0  0.5
    2010-01-01 00:00:40  10.0  45100.0  0.3
    >>> t1 = TrackObservation(df, name="fake")
    >>> t1.n_points
    5
    >>> t1.values
    array([0.1, 0.3, 0.4, 0.5, 0.3])
    >>> t1.time
    DatetimeIndex(['2010-01-01 00:00:00', '2010-01-01 00:00:10',
               '2010-01-01 00:00:20', '2010-01-01 00:00:30',
               '2010-01-01 00:00:40'],
              dtype='datetime64[ns]', name='t', freq=None)
    >>> t1.x
    array([ 0. ,  2.5,  5. ,  7.5, 10. ])
    >>> t1.y
    array([45000., 45025., 45050., 45075., 45100.])

    """

    @property
    def geometry(self):
        from shapely.geometry import MultiPoint

        """Coordinates of observation"""
        return MultiPoint(np.stack(self.x, self.y).T)

    @property
    def x(self):
        return self.data[list(self.data.data_vars)[0]].to_numpy()

    @property
    def y(self):
        return self.data[list(self.data.data_vars)[1]].to_numpy()

    @property
    def values(self):
        return self.data[list(self.data.data_vars)[2]].to_numpy()

    def __init__(
        self,
        data,
        *,
        item: Optional[int | str] = None,
        name: Optional[str] = None,
        x_item: Optional[int | str] = 0,
        y_item: Optional[int | str] = 1,
        offset_duplicates: float = 0.001,
        quantity: Optional[Quantity] = None,
    ):
        self._filename = None
        self._item = None

        if isinstance(data, (str, Path)):
            assert (
                Path(data).suffix == ".dfs0"
            ), "File must be a dfs0 file, other file types must be read with pandas or xarray"
            name = name or Path(data).stem
            data = mikeio.read(data)  # now mikeio.Dataset
        elif isinstance(data, mikeio.Dfs0):
            data = data.read()  # now mikeio.Dataset

        # parse items and convert to xr.Dataset
        items = [x_item, y_item, item]
        if isinstance(data, mikeio.Dataset):
            ds, item_names = self._mikeio_to_xarray(data, items)
            if quantity is None:
                iteminfo = data[item_names[2]].item  # 2=value item
                quantity = Quantity.from_mikeio_iteminfo(iteminfo)
        elif isinstance(data, pd.DataFrame):
            ds, item_names = self._pandas_to_xarray(data, items)
        elif isinstance(data, xr.Dataset):
            ds, item_names = self._xarray_to_xarrray(data, items)
        else:
            raise TypeError(
                f"input must be str, Path, mikeio.Dataset, pd.DataFrame or xr.Dataset! Given input has type {type(data)}"
            )

        name = name or item_names[2]

        # A unique index makes lookup much faster O(1)
        if not ds.time.to_index().is_unique:
            time = make_unique_index(
                ds.time.to_index(), offset_duplicates=offset_duplicates
            )
            ds["time"] = time

        # make sure that x and y are named x and y
        old_xy_names = list(ds.data_vars)[:2]
        ds = ds.rename(dict(zip(old_xy_names, ["x", "y"])))

        ds = ds.dropna(dim="time", subset=["x", "y"])

        super().__init__(
            name=name,
            data=ds,
            quantity=quantity,
        )

    # @staticmethod
    # def _parse_track_items(items, x_item, y_item, item):
    #     """If input has exactly 3 items we accept item=None"""
    #     if len(items) < 3:
    #         raise ValueError(
    #             f"Input has only {len(items)} items. It should have at least 3."
    #         )
    #     if item is None:
    #         if len(items) == 3:
    #             item = 2
    #         elif len(items) > 3:
    #             raise ValueError("Input has more than 3 items, but item was not given!")
    #     else:
    #         item = _parse_item(items, item)

    #     x_item = _parse_item(items, x_item, "x_item")
    #     y_item = _parse_item(items, y_item, "y_item")

    #     if (item == x_item) or (item == y_item) or (x_item == y_item):
    #         raise ValueError(
    #             f"x-item ({x_item}), y-item ({y_item}) and value-item ({item}) must be different!"
    #         )
    #     return [x_item, y_item, item]

    def _mikeio_to_xarray(self, data, items):
        assert isinstance(data, mikeio.Dataset)
        assert len(data.shape) == 1, "Only 0-dimensional data are supported"
        valid_names = [i.name for i in data.items]
        item_names = _get_item_names(items, valid_names=valid_names)
        ds = data[item_names].to_xarray()

        return ds, item_names

    def _pandas_to_xarray(self, data, items):
        assert isinstance(data, pd.DataFrame)

        item_names = _get_item_names(items, valid_names=list(data.columns))
        df = data[item_names]
        df.index.name = "time"
        return df.to_xarray(), item_names

    def _xarray_to_xarrray(self, data, items):
        assert isinstance(data, xr.Dataset)

        item_names = _get_item_names(items, valid_names=list(data.data_vars))
        ds = data[item_names]

        assert len(ds.dims) == 1, "Only 0-dimensional data are supported"

        # check that name of coords is "time", rename if not
        if ds.coords[list(ds.coords)[0]].name != "time":
            ds = ds.rename({list(ds.coords)[0]: "time"})

        return ds, item_names

    def __repr__(self):
        out = f"TrackObservation: {self.name}, n={self.n_points}"
        return out


def unit_display_name(name: str) -> str:
    """Display name

    Examples
    --------
    >>> unit_display_name("meter")
    m
    """

    res = (
        name.replace("meter", "m")
        .replace("_per_", "/")
        .replace(" per ", "/")
        .replace("second", "s")
        .replace("sec", "s")
        .replace("degree", "°")
    )

    return res
