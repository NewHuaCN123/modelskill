"""
The `observation` module contains different types of Observation classes for
fixed locations (PointObservation), or locations moving in space (TrackObservation).

Examples
--------
>>> o1 = PointObservation("klagshamn.dfs0", item=0, x=366844, y=6154291, name="Klagshamn")
"""
from __future__ import annotations

from typing import Optional
import warnings
import numpy as np
import pandas as pd
import xarray as xr

from .types import PointType, TrackType, Quantity
from .timeseries import (
    TimeSeries,
    _parse_point_input,
    _parse_track_input,
)


def _validate_attrs(data_attrs: dict, attrs: Optional[dict]) -> None:
    # See similar method in xarray https://github.com/pydata/xarray/blob/main/xarray/backends/api.py#L165

    if attrs is None:
        return
    for k, v in attrs.items():
        if k in data_attrs:
            raise ValueError(f"attrs key {k} not allowed, conflicts with build-in key!")

        # TODO: check that v is a valid type for netcdf attributes, str, int, float
        if not isinstance(v, (str, int, float)):
            raise ValueError(
                f"attrs value {v} must be a valid type for netcdf attributes, str, int, float, not {type(v)}"
            )


class Observation(TimeSeries):
    def __init__(
        self,
        data: xr.Dataset,
        weight: float = 1.0,  # TODO: cannot currently be set
        color: str = "#d62728",  # TODO: cannot currently be set
    ) -> None:
        data["time"] = self._parse_time(data.time)

        super().__init__(data=data)
        self.data[self.name].attrs["weight"] = weight
        self.data[self.name].attrs["color"] = color

    @property
    def weight(self) -> float:
        """Weighting factor for skill scores"""
        return self.data[self.name].attrs["weight"]

    @weight.setter
    def weight(self, value: float) -> None:
        self.data[self.name].attrs["weight"] = value

    # TODO: move this to TimeSeries?
    @staticmethod
    def _parse_time(time):
        if not isinstance(time.to_index(), pd.DatetimeIndex):
            raise TypeError(
                f"Input must have a datetime index! Provided index was {type(time.to_index())}"
            )
        return time.dt.round("100us")

    @property
    def _aux_vars(self):
        return list(self.data.filter_by_attrs(kind="aux").data_vars)


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
        For MIKE dfs files this is inferred from the EUM information
    aux_items : list, optional
        list of names or indices of auxiliary items, by default None
    attrs : dict, optional
        additional attributes to be added to the data, by default None

    Examples
    --------
    >>> o1 = PointObservation("klagshamn.dfs0", item=0, x=366844, y=6154291, name="Klagshamn")
    >>> o1 = PointObservation("klagshamn.dfs0", item="Water Level", x=366844, y=6154291)
    >>> o1 = PointObservation(df, item=0, x=366844, y=6154291, name="Klagshamn")
    >>> o1 = PointObservation(df["Water Level"], x=366844, y=6154291)
    """

    def __init__(
        self,
        data: PointType,
        *,
        item: Optional[int | str] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        name: Optional[str] = None,
        quantity: Optional[Quantity] = None,
        aux_items: Optional[list[int | str]] = None,
        attrs: Optional[dict] = None,
    ) -> None:
        if not self._is_input_validated(data):
            data = _parse_point_input(
                data, name=name, item=item, quantity=quantity, aux_items=aux_items
            )
            data.coords["x"] = x
            data.coords["y"] = y
            data.coords["z"] = z

        assert isinstance(data, xr.Dataset)

        data_var = str(list(data.data_vars)[0])
        data[data_var].attrs["kind"] = "observation"

        # check that user-defined attrs don't overwrite existing attrs!
        _validate_attrs(data.attrs, attrs)
        data.attrs = {**data.attrs, **(attrs or {})}

        super().__init__(data=data)

    @property
    def geometry(self):
        """Coordinates of observation (shapely.geometry.Point)"""
        from shapely.geometry import Point

        if self.z is None:
            return Point(self.x, self.y)
        else:
            return Point(self.x, self.y, self.z)

    @property
    def z(self):
        """z-coordinate of observation point"""
        return self._coordinate_values("z")

    @z.setter
    def z(self, value):
        self.data["z"] = value

    def __repr__(self):
        out = f"PointObservation: {self.name}, x={self.x}, y={self.y}"
        if len(self._aux_vars) > 0:
            out += f", aux={self._aux_vars}"
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
    keep_duplicates : (str, bool), optional
        strategy for handling duplicate timestamps (xarray.Dataset.drop_duplicates):
        "first" to keep first occurrence, "last" to keep last occurrence,
        False to drop all duplicates, "offset" to add milliseconds to
        consecutive duplicates, by default "first"
    offset_duplicates : float, optional
        DEPRECATED! in case of duplicate timestamps and keep_duplicates="offset",
        add this many seconds to consecutive duplicate entries, by default 0.001
    quantity : Quantity, optional
        The quantity of the observation, for validation with model results
        For MIKE dfs files this is inferred from the EUM information
    aux_items : list, optional
        list of names or indices of auxiliary items, by default None
    attrs : dict, optional
        additional attributes to be added to the data, by default None

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
        """Coordinates of observation (shapely.geometry.MultiPoint)"""
        from shapely.geometry import MultiPoint

        return MultiPoint(np.stack([self.x, self.y]).T)

    def __init__(
        self,
        data: TrackType,
        *,
        item: Optional[int | str] = None,
        name: Optional[str] = None,
        x_item: Optional[int | str] = 0,
        y_item: Optional[int | str] = 1,
        keep_duplicates: bool | str = "first",
        offset_duplicates: float = 0.001,
        quantity: Optional[Quantity] = None,
        aux_items: Optional[list[int | str]] = None,
        attrs: Optional[dict] = None,
    ) -> None:
        if not self._is_input_validated(data):
            if offset_duplicates != 0.001:
                warnings.warn(
                    "The 'offset_duplicates' argument is deprecated, use 'keep_duplicates' argument.",
                    FutureWarning,
                )
            data = _parse_track_input(
                data=data,
                name=name,
                item=item,
                quantity=quantity,
                x_item=x_item,
                y_item=y_item,
                keep_duplicates=keep_duplicates,
                offset_duplicates=offset_duplicates,
                aux_items=aux_items,
            )
        assert isinstance(data, xr.Dataset)

        data_var = str(list(data.data_vars)[0])
        data[data_var].attrs["kind"] = "observation"

        # check that user-defined attrs don't overwrite existing attrs!
        _validate_attrs(data.attrs, attrs)
        data.attrs = {**data.attrs, **(attrs or {})}

        super().__init__(data=data)

    def __repr__(self):
        out = f"TrackObservation: {self.name}, n={self.n_points}"
        if len(self._aux_vars) > 0:
            out += f", aux={self._aux_vars}"
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
