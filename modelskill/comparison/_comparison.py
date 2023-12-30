from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Union,
    Iterable,
    Protocol,
    Sequence,
    TYPE_CHECKING,
)
import warnings
from matplotlib.axes import Axes  # type: ignore
import numpy as np
import pandas as pd
import xarray as xr
from copy import deepcopy

from .. import metrics as mtr
from .. import Quantity, __RESERVED_NAMES
from ..types import GeometryType
from ..obs import PointObservation, TrackObservation
from ..timeseries._timeseries import _validate_data_var_name, TimeSeries
from ._comparer_plotter import ComparerPlotter
from ..metrics import _parse_metric

from ._utils import (
    _add_spatial_grid_to_df,
    _groupby_df,
    _parse_groupby,
    TimeTypes,
    IdOrNameTypes,
)
from ..skill import SkillTable
from ..skill_grid import SkillGrid
from ..settings import register_option
from ..utils import _get_name
from .. import __version__

if TYPE_CHECKING:
    from ._collection import ComparerCollection


class Scoreable(Protocol):
    def score(self, metric: str | Callable, **kwargs) -> Dict[str, float]:
        ...

    def skill(
        self,
        by: str | Iterable[str] | None = None,
        metrics: Iterable[str] | Iterable[Callable] | str | Callable | None = None,
        **kwargs,
    ) -> SkillTable:
        ...

    def gridded_skill(
        self,
        bins: int = 5,
        binsize: float | None = None,
        by: str | Iterable[str] | None = None,
        metrics: Iterable[str] | Iterable[Callable] | str | Callable | None = None,
        n_min: int | None = None,
        **kwargs,
    ) -> SkillGrid:
        ...


def _parse_dataset(data) -> xr.Dataset:
    if not isinstance(data, xr.Dataset):
        raise ValueError("matched_data must be an xarray.Dataset")
        # matched_data = self._matched_data_to_xarray(matched_data)
    assert "Observation" in data.data_vars

    # no missing values allowed in Observation
    if data["Observation"].isnull().any():
        raise ValueError("Observation data must not contain missing values.")

    # coordinates
    if "x" not in data.coords:
        data.coords["x"] = np.nan
    if "y" not in data.coords:
        data.coords["y"] = np.nan
    if "z" not in data.coords:
        data.coords["z"] = np.nan

    # Validate data
    vars = [v for v in data.data_vars]
    assert len(vars) > 1, "dataset must have at least two data arrays"

    for v in data.data_vars:
        v = _validate_data_var_name(str(v))
        assert (
            len(data[v].dims) == 1
        ), f"Only 0-dimensional data arrays are supported! {v} has {len(data[v].dims)} dimensions"
        assert (
            list(data[v].dims)[0] == "time"
        ), f"All data arrays must have a time dimension; {v} has dimensions {data[v].dims}"
        if "kind" not in data[v].attrs:
            data[v].attrs["kind"] = "auxiliary"

    n_mod = sum([_is_model(da) for da in data.data_vars.values()])
    n_obs = sum([_is_observation(da) for da in data.data_vars.values()])

    # Validate observation data array
    if n_obs != 1:
        raise ValueError(
            f"dataset must have exactly one observation array (marked by the kind attribute), this has {n_obs}"
        )
    if n_mod == 0:
        raise ValueError(
            "dataset must have at least one model array (marked by the kind attribute)"
        )

    # Validate attrs
    if "gtype" not in data.attrs:
        data.attrs["gtype"] = str(GeometryType.POINT)
    # assert "gtype" in data.attrs, "data must have a gtype attribute"
    # assert data.attrs["gtype"] in [
    #     str(GeometryType.POINT),
    #     str(GeometryType.TRACK),
    # ], f"data attribute 'gtype' must be one of {GeometryType.POINT} or {GeometryType.TRACK}"

    if "color" not in data["Observation"].attrs:
        data["Observation"].attrs["color"] = "black"

    if "long_name" not in data["Observation"].attrs:
        data["Observation"].attrs["long_name"] = Quantity.undefined().name

    if "units" not in data["Observation"].attrs:
        data["Observation"].attrs["units"] = Quantity.undefined().unit

    data.attrs["modelskill_version"] = __version__

    if "weight" not in data.attrs:
        data.attrs["weight"] = 1.0
    return data


def _is_observation(da: xr.DataArray) -> bool:
    return da.attrs["kind"] == "observation"


def _is_model(da: xr.DataArray) -> bool:
    return da.attrs["kind"] == "model"


# TODO remove in v1.1
def _get_deprecated_args(kwargs):
    model, start, end, area = None, None, None, None

    # Don't bother refactoring this, it will be removed in v1.1
    if "model" in kwargs:
        model = kwargs.pop("model")
        if model is not None:
            warnings.warn(
                f"The 'model' argument is deprecated, use 'sel(model='{model}')' instead",
                FutureWarning,
            )

    if "start" in kwargs:
        start = kwargs.pop("start")

        if start is not None:
            warnings.warn(
                f"The 'start' argument is deprecated, use 'sel(start={start})' instead",
                FutureWarning,
            )

    if "end" in kwargs:
        end = kwargs.pop("end")

        if end is not None:
            warnings.warn(
                f"The 'end' argument is deprecated, use 'sel(end={end})' instead",
                FutureWarning,
            )

    if "area" in kwargs:
        area = kwargs.pop("area")

        if area is not None:
            warnings.warn(
                f"The 'area' argument is deprecated, use 'sel(area={area})' instead",
                FutureWarning,
            )

    return model, start, end, area


def _validate_metrics(metrics) -> None:
    for m in metrics:
        if isinstance(m, str):
            if not mtr.is_valid_metric(m):
                raise ValueError(
                    f"Unknown metric '{m}'! Supported metrics are: {mtr.defined_metrics}"
                )


register_option(
    key="metrics.list",
    defval=mtr.default_metrics,
    validator=_validate_metrics,
    doc="Default metrics list to be used in skill tables if specific metrics are not provided.",
)

MOD_COLORS = (
    "#1f78b4",
    "#33a02c",
    "#ff7f00",
    "#93509E",
    "#63CEFF",
    "#fdbf6f",
    "#004165",
    "#8B8D8E",
    "#0098DB",
    "#61C250",
    "#a6cee3",
    "#b2df8a",
    "#fb9a99",
    "#cab2d6",
    "#003f5c",
    "#2f4b7c",
    "#665191",
    "#e31a1c",
)


@dataclass
class ItemSelection:
    "Utility class to keep track of observation, model and auxiliary items"
    obs: str
    model: Sequence[str]
    aux: Sequence[str]

    def __post_init__(self):
        # check that obs, model and aux are unique, and that they are not overlapping
        all_items = self.all
        if len(all_items) != len(set(all_items)):
            raise ValueError("Items must be unique")

    @property
    def all(self) -> Sequence[str]:
        return [self.obs] + list(self.model) + list(self.aux)

    @staticmethod
    def parse(
        items: List[str],
        obs_item: str | int | None = None,
        mod_items: Optional[Iterable[str | int]] = None,
        aux_items: Optional[Iterable[str | int]] = None,
    ) -> ItemSelection:
        """Parse items and return observation, model and auxiliary items
        Default behaviour:
        - obs_item is first item
        - mod_items are all but obs_item and aux_items
        - aux_items are None

        Both integer and str are accepted as items. If str, it must be a key in data.
        """
        assert len(items) > 1, "data must contain at least two items"
        if obs_item is None:
            obs_name: str = items[0]
        else:
            obs_name = _get_name(obs_item, items)

        # Check existance of items and convert to names
        if mod_items is not None:
            if isinstance(mod_items, (str, int)):
                mod_items = [mod_items]
            mod_names = [_get_name(m, items) for m in mod_items]
        if aux_items is not None:
            if isinstance(aux_items, (str, int)):
                aux_items = [aux_items]
            aux_names = [_get_name(a, items) for a in aux_items]
        else:
            aux_names = []

        items.remove(obs_name)

        if mod_items is None:
            mod_names = list(set(items) - set(aux_names))

        assert len(mod_names) > 0, "no model items were found! Must be at least one"
        assert obs_name not in mod_names, "observation item must not be a model item"
        assert (
            obs_name not in aux_names
        ), "observation item must not be an auxiliary item"
        assert isinstance(obs_name, str), "observation item must be a string"

        return ItemSelection(obs=obs_name, model=mod_names, aux=aux_names)


def _area_is_bbox(area) -> bool:
    is_bbox = False
    if area is not None:
        if not np.isscalar(area):
            area = np.array(area)
            if (area.ndim == 1) & (len(area) == 4):
                if np.all(np.isreal(area)):
                    is_bbox = True
    return is_bbox


def _area_is_polygon(area) -> bool:
    if area is None:
        return False
    if np.isscalar(area):
        return False
    if not np.all(np.isreal(area)):
        return False
    polygon = np.array(area)
    if polygon.ndim > 2:
        return False

    if polygon.ndim == 1:
        if len(polygon) <= 5:
            return False
        if len(polygon) % 2 != 0:
            return False

    if polygon.ndim == 2:
        if polygon.shape[0] < 3:
            return False
        if polygon.shape[1] != 2:
            return False

    return True


def _inside_polygon(polygon, xy) -> np.ndarray:
    import matplotlib.path as mp  # type: ignore

    if polygon.ndim == 1:
        polygon = np.column_stack((polygon[0::2], polygon[1::2]))
    return mp.Path(polygon).contains_points(xy)


def _matched_data_to_xarray(
    df: pd.DataFrame,
    obs_item: int | str | None = None,
    mod_items: Optional[Iterable[str | int]] = None,
    aux_items: Optional[Iterable[str | int]] = None,
    name: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    z: Optional[float] = None,
    quantity: Optional[Quantity] = None,
):
    """Convert matched data to accepted xarray.Dataset format"""
    assert isinstance(df, pd.DataFrame)
    cols = list(df.columns)
    items = ItemSelection.parse(cols, obs_item, mod_items, aux_items)

    # check that items.obs and items.model are numeric
    if not np.issubdtype(df[items.obs].dtype, np.number):
        raise ValueError(
            "Observation data is of type {df[items.obs].dtype}, it must be numeric"
        )
    for m in items.model:
        if not np.issubdtype(df[m].dtype, np.number):
            raise ValueError(
                f"Model data: {m} is of type {df[m].dtype}, it must be numeric"
            )

    df = df[items.all]
    df.index.name = "time"
    df = df.rename(columns={items.obs: "Observation"})
    ds = df.to_xarray()

    ds.attrs["name"] = name if name is not None else items.obs
    ds["Observation"].attrs["kind"] = "observation"
    for m in items.model:
        ds[m].attrs["kind"] = "model"
    for a in items.aux:
        ds[a].attrs["kind"] = "auxiliary"

    if x is not None:
        ds.coords["x"] = x
    if y is not None:
        ds.coords["y"] = y
    if z is not None:
        ds.coords["z"] = z

    if x is None or np.isscalar(x):
        ds.attrs["gtype"] = str(GeometryType.POINT)
    else:
        ds.attrs["gtype"] = str(GeometryType.TRACK)

    if quantity is None:
        q = Quantity.undefined()
    else:
        q = quantity

    ds["Observation"].attrs["long_name"] = q.name
    ds["Observation"].attrs["units"] = q.unit
    ds["Observation"].attrs["is_directional"] = int(q.is_directional)

    return ds


class Comparer(Scoreable):
    """
    Comparer class for comparing model and observation data.

    Typically, the Comparer is part of a ComparerCollection,
    created with the `match` function.

    Parameters
    ----------
    matched_data : xr.Dataset
        Matched data
    raw_mod_data : dict of modelskill.TimeSeries, optional
        Raw model data. If None, observation and modeldata must be provided.

    Examples
    --------
    >>> import modelskill as ms
    >>> cmp1 = ms.match(observation, modeldata)
    >>> cmp2 = ms.from_matched(matched_data)

    See Also
    --------
    modelskill.match, modelskill.from_matched
    """

    data: xr.Dataset
    raw_mod_data: Dict[str, TimeSeries]
    _obs_str = "Observation"
    plotter = ComparerPlotter

    def __init__(
        self,
        matched_data: xr.Dataset,
        raw_mod_data: Optional[Dict[str, TimeSeries]] = None,
    ) -> None:
        self.data = _parse_dataset(matched_data)
        self.raw_mod_data = (
            raw_mod_data
            if raw_mod_data is not None
            else {
                # key: ModelResult(value, gtype=self.data.gtype, name=key, x=self.x, y=self.y)
                key: TimeSeries(self.data[[key]])
                for key, value in matched_data.data_vars.items()
                if value.attrs["kind"] == "model"
            }
        )
        # TODO: validate that the names in raw_mod_data are the same as in matched_data
        assert isinstance(self.raw_mod_data, dict)
        for k in self.raw_mod_data.keys():
            v = self.raw_mod_data[k]
            if not isinstance(v, TimeSeries):
                try:
                    self.raw_mod_data[k] = TimeSeries(v)
                except Exception:
                    raise ValueError(
                        f"raw_mod_data[{k}] could not be converted to a TimeSeries object"
                    )
            else:
                assert isinstance(
                    v, TimeSeries
                ), f"raw_mod_data[{k}] must be a TimeSeries object"

        self.plot = Comparer.plotter(self)

    @staticmethod
    def from_matched_data(
        data: xr.Dataset | pd.DataFrame,
        raw_mod_data: Optional[Dict[str, TimeSeries]] = None,
        obs_item: str | int | None = None,
        mod_items: Optional[Iterable[str | int]] = None,
        aux_items: Optional[Iterable[str | int]] = None,
        name: Optional[str] = None,
        weight: float = 1.0,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        quantity: Optional[Quantity] = None,
    ) -> "Comparer":
        """Initialize from compared data"""
        if not isinstance(data, xr.Dataset):
            # TODO: handle raw_mod_data by accessing data.attrs["kind"] and only remove nan after
            data = _matched_data_to_xarray(
                data,
                obs_item=obs_item,
                mod_items=mod_items,
                aux_items=aux_items,
                name=name,
                x=x,
                y=y,
                z=z,
                quantity=quantity,
            )
            data.attrs["weight"] = weight
        return Comparer(matched_data=data, raw_mod_data=raw_mod_data)

    def __repr__(self):
        out = [
            f"<{type(self).__name__}>",
            f"Quantity: {self.quantity}",
            f"Observation: {self.name}, n_points={self.n_points}",
        ]
        for model in self.mod_names:
            out.append(f" Model: {model}, rmse={self.score()[model]:.3f}")

        for var in self.aux_names:
            out.append(f" Auxiliary: {var}")
        return str.join("\n", out)

    @property
    def name(self) -> str:
        """Name of comparer (=name of observation)"""
        return self.data.attrs["name"]

    @name.setter
    def name(self, name: str) -> None:
        if name in __RESERVED_NAMES:
            raise ValueError(
                f"Cannot rename to any of {__RESERVED_NAMES}, these are reserved names!"
            )
        self.data.attrs["name"] = name

    @property
    def gtype(self) -> str:
        """Geometry type"""
        return self.data.attrs["gtype"]

    @property
    def quantity(self) -> Quantity:
        """Quantity object"""
        return Quantity(
            name=self.data[self._obs_str].attrs["long_name"],
            unit=self.data[self._obs_str].attrs["units"],
            is_directional=bool(
                self.data[self._obs_str].attrs.get("is_directional", False)
            ),
        )

    @quantity.setter
    def quantity(self, quantity: Quantity) -> None:
        assert isinstance(quantity, Quantity), "value must be a Quantity object"
        self.data[self._obs_str].attrs["long_name"] = quantity.name
        self.data[self._obs_str].attrs["units"] = quantity.unit
        self.data[self._obs_str].attrs["is_directional"] = int(quantity.is_directional)

    @property
    def n_points(self) -> int:
        """number of compared points"""
        return len(self.data[self._obs_str]) if self.data else 0

    @property
    def time(self) -> pd.DatetimeIndex:
        """time of compared data as pandas DatetimeIndex"""
        return self.data.time.to_index()

    # TODO: Should we keep these? (renamed to start_time and end_time)
    # @property
    # def start(self) -> pd.Timestamp:
    #     """start pd.Timestamp of compared data"""
    #     return self.time[0]

    # @property
    # def end(self) -> pd.Timestamp:
    #     """end pd.Timestamp of compared data"""
    #     return self.time[-1]

    @property
    def x(self):
        """x-coordinate"""
        return self._coordinate_values("x")

    @property
    def y(self):
        """y-coordinate"""
        return self._coordinate_values("y")

    @property
    def z(self):
        """z-coordinate"""
        return self._coordinate_values("z")

    def _coordinate_values(self, coord):
        vals = self.data[coord].values
        return np.atleast_1d(vals)[0] if vals.ndim == 0 else vals

    @property
    def n_models(self) -> int:
        """Number of model results"""
        return len(self.mod_names)

    @property
    def mod_names(self) -> Sequence[str]:
        """List of model result names"""
        return list(self.raw_mod_data.keys())

    @property
    def aux_names(self) -> Sequence[str]:
        """List of auxiliary data names"""
        return list(
            [
                k
                for k, v in self.data.data_vars.items()
                if v.attrs["kind"] not in ["observation", "model"]
            ]
        )

    # TODO: always "Observation", necessary to have this property?
    @property
    def _obs_name(self) -> str:
        return self._obs_str

    @property
    def weight(self) -> float:
        """Weight of observation (used in ComparerCollection score() and mean_skill())"""
        return self.data.attrs["weight"]

    @weight.setter
    def weight(self, value: float) -> None:
        self.data.attrs["weight"] = value

    @property
    def unit_text(self) -> str:
        """Quantity name and unit as text suitable for plot labels"""
        return f"{self.quantity.name} [{self.quantity.unit}]"

    def _model_to_frame(self, mod_name: str) -> pd.DataFrame:
        """Convert single model data to pandas DataFrame"""

        df = self.data.drop_vars(["z"]).to_dataframe().copy()
        other_models = [m for m in self.mod_names if m is not mod_name]
        df = df.drop(columns=other_models)
        df = df.rename(columns={mod_name: "mod_val", self._obs_str: "obs_val"})
        df["model"] = mod_name
        df["observation"] = self.name

        return df

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to pandas DataFrame with all model data concatenated"""

        # TODO is this needed?, comment out for now
        # df = df.sort_index()
        df = pd.concat([self._model_to_frame(name) for name in self.mod_names])
        df["model"] = df["model"].astype("category")
        df["observation"] = df["observation"].astype("category")
        return df

    # TODO: is this the best way to copy (self.data.copy.. )
    def __copy__(self):
        return deepcopy(self)

    def copy(self):
        return self.__copy__()

    def rename(self, mapping: Mapping[str, str]) -> "Comparer":
        """Rename observation, model or auxiliary data variables

        Parameters
        ----------
        mapping : dict
            mapping of old names to new names

        Returns
        -------
        Comparer

        Examples
        --------
        >>> cmp = ms.match(observation, modeldata)
        >>> cmp.mod_names
        ['model1']
        >>> cmp2 = cmp.rename({'model1': 'model2'})
        >>> cmp2.mod_names
        ['model2']
        """
        if any([k in __RESERVED_NAMES for k in mapping.values()]):
            raise ValueError(
                f"Cannot rename to any of {__RESERVED_NAMES}, these are reserved names!"
            )

        for k in mapping.keys():
            if k == self.name:
                self.name = mapping[k]
                mapping.pop(k)
                break

        data = self.data.rename(mapping)
        raw_mod_data = {mapping.get(k, k): v for k, v in self.raw_mod_data.items()}

        return Comparer(matched_data=data, raw_mod_data=raw_mod_data)

    def save(self, filename: Union[str, Path]) -> None:
        """Save to netcdf file

        Parameters
        ----------
        filename : str or Path
            filename
        """
        ds = self.data

        # add self.raw_mod_data to ds with prefix 'raw_' to avoid name conflicts
        # an alternative strategy would be to use NetCDF groups
        # https://docs.xarray.dev/en/stable/user-guide/io.html#groups

        # There is no need to save raw data for track data, since it is identical to the matched data
        if self.gtype == "point":
            ds = self.data.copy()  # copy needed to avoid modifying self.data

            for key, ts_mod in self.raw_mod_data.items():
                ts_mod = ts_mod.copy()
                #  rename time to unique name
                ts_mod.data = ts_mod.data.rename({"time": "_time_raw_" + key})
                # da = ds_mod.to_xarray()[key]
                ds["_raw_" + key] = ts_mod.data[key]

        ds.to_netcdf(filename)

    @staticmethod
    def load(filename: Union[str, Path]) -> "Comparer":
        """Load from netcdf file

        Parameters
        ----------
        filename : str or Path
            filename

        Returns
        -------
        Comparer
        """
        with xr.open_dataset(filename) as ds:
            data = ds.load()

        if data.gtype == "track":
            return Comparer(matched_data=data)

        if data.gtype == "point":
            raw_mod_data: Dict[str, TimeSeries] = {}

            for var in data.data_vars:
                var_name = str(var)
                if var_name[:5] == "_raw_":
                    new_key = var_name[5:]  # remove prefix '_raw_'
                    ds = data[[var_name]].rename(
                        {"_time_raw_" + new_key: "time", var_name: new_key}
                    )
                    ts = PointObservation(data=ds, name=new_key)
                    # TODO: name of time?
                    # ts.name = new_key
                    # df = (
                    #     data[var_name]
                    #     .to_dataframe()
                    #     .rename(
                    #         columns={"_time_raw_" + new_key: "time", var_name: new_key}
                    #     )
                    # )
                    raw_mod_data[new_key] = ts

                    # data = data.drop(var_name).drop("_time_raw_" + new_key)

            # filter variables, only keep the ones with a 'time' dimension
            data = data[[v for v in data.data_vars if "time" in data[v].dims]]

            return Comparer(matched_data=data, raw_mod_data=raw_mod_data)

        else:
            raise NotImplementedError(f"Unknown gtype: {data.gtype}")

    def _to_observation(self) -> PointObservation | TrackObservation:
        """Convert to Observation"""
        if self.gtype == "point":
            df = self.data.drop_vars(["x", "y", "z"])[self._obs_str].to_dataframe()
            return PointObservation(
                data=df,
                name=self.name,
                x=self.x,
                y=self.y,
                z=self.z,
                quantity=self.quantity,
                # TODO: add attrs
            )
        elif self.gtype == "track":
            df = self.data.drop_vars(["z"])[[self._obs_str]].to_dataframe()
            return TrackObservation(
                data=df,
                item=0,
                x_item=1,
                y_item=2,
                name=self.name,
                quantity=self.quantity,
                # TODO: add attrs
            )
        else:
            raise NotImplementedError(f"Unknown gtype: {self.gtype}")

    def __add__(
        self, other: Union["Comparer", "ComparerCollection"]
    ) -> "ComparerCollection":
        from ._collection import ComparerCollection
        from ..matching import match_space_time

        if not isinstance(other, (Comparer, ComparerCollection)):
            raise TypeError(f"Cannot add {type(other)} to {type(self)}")

        if isinstance(other, Comparer) and (self.name == other.name):
            assert type(self) == type(other), "Must be same type!"
            missing_models = set(self.mod_names) - set(other.mod_names)
            if len(missing_models) == 0:
                # same obs name and same model names
                cmp = self.copy()
                cmp.data = xr.concat([cmp.data, other.data], dim="time")
                # cc.data = cc.data[
                #    ~cc.data.time.to_index().duplicated(keep="last")
                # ]  # 'first'
                _, index = np.unique(cmp.data["time"], return_index=True)
                cmp.data = cmp.data.isel(time=index)

            else:
                raw_mod_data = self.raw_mod_data.copy()
                raw_mod_data.update(other.raw_mod_data)  # TODO!
                matched = match_space_time(
                    observation=self._to_observation(), raw_mod_data=raw_mod_data  # type: ignore
                )
                cmp = Comparer(matched_data=matched, raw_mod_data=raw_mod_data)

            return cmp
        else:
            if isinstance(other, Comparer):
                return ComparerCollection([self, other])
            elif isinstance(other, ComparerCollection):
                return ComparerCollection([self, *other])

    def sel(
        self,
        model: Optional[IdOrNameTypes] = None,
        start: Optional[TimeTypes] = None,
        end: Optional[TimeTypes] = None,
        time: Optional[TimeTypes] = None,
        area: Optional[List[float]] = None,
    ) -> "Comparer":
        """Select data based on model, time and/or area.

        Parameters
        ----------
        model : str or int or list of str or list of int, optional
            Model name or index. If None, all models are selected.
        start : str or datetime, optional
            Start time. If None, all times are selected.
        end : str or datetime, optional
            End time. If None, all times are selected.
        time : str or datetime, optional
            Time. If None, all times are selected.
        area : list of float, optional
            bbox: [x0, y0, x1, y1] or Polygon. If None, all areas are selected.

        Returns
        -------
        Comparer
            New Comparer with selected data.
        """
        if (time is not None) and ((start is not None) or (end is not None)):
            raise ValueError("Cannot use both time and start/end")

        d = self.data
        raw_mod_data = self.raw_mod_data
        if model is not None:
            if isinstance(model, (str, int)):
                models = [model]
            else:
                models = list(model)
            mod_names: List[str] = [_get_name(m, self.mod_names) for m in models]
            dropped_models = [m for m in self.mod_names if m not in mod_names]
            d = d.drop_vars(dropped_models)
            raw_mod_data = {m: raw_mod_data[m] for m in mod_names}
        if (start is not None) or (end is not None):
            # TODO: can this be done without to_index? (simplify)
            d = d.sel(time=d.time.to_index().to_frame().loc[start:end].index)  # type: ignore

            # Note: if user asks for a specific time, we also filter raw
            raw_mod_data = {k: v.sel(time=slice(start, end)) for k, v in raw_mod_data.items()}  # type: ignore
        if time is not None:
            d = d.sel(time=time)

            # Note: if user asks for a specific time, we also filter raw
            raw_mod_data = {k: v.sel(time=time) for k, v in raw_mod_data.items()}
        if area is not None:
            if _area_is_bbox(area):
                x0, y0, x1, y1 = area
                mask = (d.x > x0) & (d.x < x1) & (d.y > y0) & (d.y < y1)
            elif _area_is_polygon(area):
                polygon = np.array(area)
                xy = np.column_stack((d.x, d.y))
                mask = _inside_polygon(polygon, xy)
            else:
                raise ValueError("area supports bbox [x0,y0,x1,y1] and closed polygon")
            if self.gtype == "point":
                # if False, return empty data
                d = d if mask else d.isel(time=slice(None, 0))
            else:
                d = d.isel(time=mask)
        return Comparer.from_matched_data(data=d, raw_mod_data=raw_mod_data)

    def where(
        self,
        cond: Union[bool, np.ndarray, xr.DataArray],
    ) -> "Comparer":
        """Return a new Comparer with values where cond is True

        Parameters
        ----------
        cond : bool, np.ndarray, xr.DataArray
            This selects the values to return.

        Returns
        -------
        Comparer
            New Comparer with values where cond is True and other otherwise.

        Examples
        --------
        >>> c2 = c.where(c.data.Observation > 0)
        """
        d = self.data.where(cond, other=np.nan)
        d = d.dropna(dim="time", how="all")
        return Comparer.from_matched_data(d, self.raw_mod_data)

    def query(self, query: str) -> "Comparer":
        """Return a new Comparer with values where query cond is True

        Parameters
        ----------
        query : str
            Query string, see pandas.DataFrame.query

        Returns
        -------
        Comparer
            New Comparer with values where cond is True and other otherwise.

        Examples
        --------
        >>> c2 = c.query("Observation > 0")
        """
        d = self.data.query({"time": query})
        d = d.dropna(dim="time", how="all")
        return Comparer.from_matched_data(d, self.raw_mod_data)

    def skill(
        self,
        by: str | Iterable[str] | None = None,
        metrics: Iterable[str] | Iterable[Callable] | str | Callable | None = None,
        **kwargs,
    ) -> SkillTable:
        """Skill assessment of model(s)

        Parameters
        ----------
        by : (str, List[str]), optional
            group by column name or by temporal bin via the freq-argument
            (using pandas pd.Grouper(freq)),
            e.g.: 'freq:M' = monthly; 'freq:D' daily
            by default ["model"]
        metrics : list, optional
            list of modelskill.metrics, by default modelskill.options.metrics.list

        Returns
        -------
        SkillTable
            skill assessment object

        See also
        --------
        sel
            a method for filtering/selecting data

        Examples
        --------
        >>> import modelskill as ms
        >>> cc = ms.match(c2, mod)
        >>> cc['c2'].skill().round(2)
                       n  bias  rmse  urmse   mae    cc    si    r2
        observation
        c2           113 -0.00  0.35   0.35  0.29  0.97  0.12  0.99

        >>> cc['c2'].skill(by='freq:D').round(2)
                     n  bias  rmse  urmse   mae    cc    si    r2
        2017-10-27  72 -0.19  0.31   0.25  0.26  0.48  0.12  0.98
        2017-10-28   0   NaN   NaN    NaN   NaN   NaN   NaN   NaN
        2017-10-29  41  0.33  0.41   0.25  0.36  0.96  0.06  0.99
        """
        metrics = _parse_metric(metrics, directional=self.quantity.is_directional)

        # TODO remove in v1.1
        model, start, end, area = _get_deprecated_args(kwargs)
        assert kwargs == {}, f"Unknown keyword arguments: {kwargs}"

        cmp = self.sel(
            model=model,
            start=start,
            end=end,
            area=area,
        )
        if cmp.n_points == 0:
            raise ValueError("No data selected for skill assessment")

        by = _parse_groupby(by, cmp.n_models, n_obs=1, n_var=1)

        df = cmp.to_dataframe()
        res = _groupby_df(df, by, metrics)
        res["x"] = df.groupby(by=by, observed=False).x.first()
        res["y"] = df.groupby(by=by, observed=False).y.first()
        # TODO: set x,y to NaN if TrackObservation
        res = self._add_as_col_if_not_in_index(df, skilldf=res)
        return SkillTable(res)

    def _add_as_col_if_not_in_index(self, df, skilldf):
        """Add a field to skilldf if unique in df"""
        FIELDS = ("observation", "model")

        for field in FIELDS:
            if (field == "model") and (self.n_models <= 1):
                continue
            if field not in skilldf.index.names:
                unames = df[field].unique()
                if len(unames) == 1:
                    skilldf.insert(loc=0, column=field, value=unames[0])
        return skilldf

    def score(
        self,
        metric: str | Callable = mtr.rmse,
        **kwargs,
    ) -> Dict[str, float]:
        """Model skill score

        Parameters
        ----------
        metric : list, optional
            a single metric from modelskill.metrics, by default rmse

        Returns
        -------
        float
            skill score as a single number (for each model)

        See also
        --------
        skill
            a method for skill assessment returning a pd.DataFrame

        Examples
        --------
        >>> import modelskill as ms
        >>> cmp = ms.match(c2, mod)
        >>> cmp.score()
        0.3517964910888918

        >>> cmp.score(metric=ms.metrics.mape)
        11.567399646108198
        """
        metric = _parse_metric(metric)[0]
        if not (callable(metric) or isinstance(metric, str)):
            raise ValueError("metric must be a string or a function")

        # TODO remove in v1.1
        model, start, end, area = _get_deprecated_args(kwargs)
        assert kwargs == {}, f"Unknown keyword arguments: {kwargs}"

        s = self.skill(
            by=["model", "observation"],
            metrics=[metric],
            model=model,  # deprecated
            start=start,  # deprecated
            end=end,  # deprecated
            area=area,  # deprecated
        )
        df = s.to_dataframe()

        metric_name = metric if isinstance(metric, str) else metric.__name__

        return (
            df.reset_index()
            .groupby("model", observed=True)[metric_name]
            .mean()
            .to_dict()
        )

    def spatial_skill(
        self,
        bins=5,
        binsize=None,
        by=None,
        metrics=None,
        n_min=None,
        **kwargs,
    ):
        # deprecated
        warnings.warn(
            "spatial_skill is deprecated, use gridded_skill instead", FutureWarning
        )
        return self.gridded_skill(
            bins=bins,
            binsize=binsize,
            by=by,
            metrics=metrics,
            n_min=n_min,
            **kwargs,
        )

    def gridded_skill(
        self,
        bins: int = 5,
        binsize: float | None = None,
        by: str | Iterable[str] | None = None,
        metrics: Iterable[str] | Iterable[Callable] | str | Callable | None = None,
        n_min: int | None = None,
        **kwargs,
    ):
        """Aggregated spatial skill assessment of model(s) on a regular spatial grid.

        Parameters
        ----------
        bins: int, list of scalars, or IntervalIndex, or tuple of, optional
            criteria to bin x and y by, argument bins to pd.cut(), default 5
            define different bins for x and y a tuple
            e.g.: bins = 5, bins = (5,[2,3,5])
        binsize : float, optional
            bin size for x and y dimension, overwrites bins
            creates bins with reference to round(mean(x)), round(mean(y))
        by : (str, List[str]), optional
            group by column name or by temporal bin via the freq-argument
            (using pandas pd.Grouper(freq)),
            e.g.: 'freq:M' = monthly; 'freq:D' daily
            by default ["model","observation"]
        metrics : list, optional
            list of modelskill.metrics, by default modelskill.options.metrics.list
        n_min : int, optional
            minimum number of observations in a grid cell;
            cells with fewer observations get a score of `np.nan`

        Returns
        -------
        xr.Dataset
            skill assessment as a dataset

        See also
        --------
        skill
            a method for aggregated skill assessment

        Examples
        --------
        >>> import modelskill as ms
        >>> cmp = ms.match(c2, mod)   # satellite altimeter vs. model
        >>> cmp.gridded_skill(metrics='bias')
        <xarray.Dataset>
        Dimensions:      (x: 5, y: 5)
        Coordinates:
            observation   'alti'
        * x            (x) float64 -0.436 1.543 3.517 5.492 7.466
        * y            (y) float64 50.6 51.66 52.7 53.75 54.8
        Data variables:
            n            (x, y) int32 3 0 0 14 37 17 50 36 72 ... 0 0 15 20 0 0 0 28 76
            bias         (x, y) float64 -0.02626 nan nan ... nan 0.06785 -0.1143

        >>> ds = cc.gridded_skill(binsize=0.5)
        >>> ds.coords
        Coordinates:
            observation   'alti'
        * x            (x) float64 -1.5 -0.5 0.5 1.5 2.5 3.5 4.5 5.5 6.5 7.5
        * y            (y) float64 51.5 52.5 53.5 54.5 55.5 56.5
        """

        # TODO remove in v1.1
        model, start, end, area = _get_deprecated_args(kwargs)
        assert kwargs == {}, f"Unknown keyword arguments: {kwargs}"

        cmp = self.sel(
            model=model,
            start=start,
            end=end,
            area=area,
        )

        metrics = _parse_metric(metrics)
        if cmp.n_points == 0:
            raise ValueError("No data to compare")

        df = cmp.to_dataframe()
        df = _add_spatial_grid_to_df(df=df, bins=bins, binsize=binsize)

        # n_models = len(df.model.unique())
        # n_obs = len(df.observation.unique())

        # n_obs=1 because we only have one observation (**SingleObsComparer**)
        by = _parse_groupby(by=by, n_models=cmp.n_models, n_obs=1)
        if isinstance(by, str) or (not isinstance(by, Iterable)):
            by = [by]  # type: ignore
        if "x" not in by:  # type: ignore
            by.insert(0, "x")  # type: ignore
        if "y" not in by:  # type: ignore
            by.insert(0, "y")  # type: ignore
        assert isinstance(by, list)

        df = df.drop(columns=["x", "y"]).rename(columns=dict(xBin="x", yBin="y"))
        res = _groupby_df(df, by, metrics, n_min)
        ds = res.to_xarray().squeeze()

        # change categorial index to coordinates
        for dim in ("x", "y"):
            ds[dim] = ds[dim].astype(float)

        return SkillGrid(ds)

    @property
    def residual(self):
        df = self.data.drop_vars(["x", "y", "z"]).to_dataframe()
        obs = df[self._obs_str].values
        mod = df[self.mod_names].values
        return mod - np.vstack(obs)

    def remove_bias(self, correct="Model") -> Comparer:
        cmp = self.copy()

        bias = cmp.residual.mean(axis=0)
        if correct == "Model":
            for j in range(cmp.n_models):
                mod_name = cmp.mod_names[j]
                mod_ts = cmp.raw_mod_data[mod_name]
                with xr.set_options(keep_attrs=True):
                    mod_ts.data[mod_name].values = mod_ts.values - bias[j]
                    cmp.data[mod_name].values = cmp.data[mod_name].values - bias[j]
        elif correct == "Observation":
            # what if multiple models?
            with xr.set_options(keep_attrs=True):
                cmp.data[cmp._obs_str].values = cmp.data[cmp._obs_str].values + bias
        else:
            raise ValueError(
                f"Unknown correct={correct}. Only know 'Model' and 'Observation'"
            )
        return cmp

    # TODO remove plotting methods in v1.1
    def scatter(
        self,
        *,
        bins=120,
        quantiles=None,
        fit_to_quantiles=False,
        show_points=None,
        show_hist=None,
        show_density=None,
        norm=None,
        backend="matplotlib",
        figsize=(8, 8),
        xlim=None,
        ylim=None,
        reg_method="ols",
        title=None,
        xlabel=None,
        ylabel=None,
        skill_table=None,
        **kwargs,
    ):
        warnings.warn(
            "This method is deprecated, use plot.scatter instead", FutureWarning
        )

        # TODO remove in v1.1
        model, start, end, area = _get_deprecated_args(kwargs)

        # self.plot.scatter(
        self.sel(
            model=model,
            start=start,
            end=end,
            area=area,
        ).plot.scatter(
            bins=bins,
            quantiles=quantiles,
            fit_to_quantiles=fit_to_quantiles,
            show_points=show_points,
            show_hist=show_hist,
            show_density=show_density,
            norm=norm,
            backend=backend,
            figsize=figsize,
            xlim=xlim,
            ylim=ylim,
            reg_method=reg_method,
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            **kwargs,
        )

    def taylor(
        self,
        normalize_std=False,
        figsize=(7, 7),
        marker="o",
        marker_size=6.0,
        title="Taylor diagram",
        **kwargs,
    ):
        warnings.warn("taylor is deprecated, use plot.taylor instead", FutureWarning)

        self.plot.taylor(
            normalize_std=normalize_std,
            figsize=figsize,
            marker=marker,
            marker_size=marker_size,
            title=title,
            **kwargs,
        )

    def hist(
        self, *, model=None, bins=100, title=None, density=True, alpha=0.5, **kwargs
    ):
        warnings.warn("hist is deprecated. Use plot.hist instead.", FutureWarning)
        return self.plot.hist(
            model=model, bins=bins, title=title, density=density, alpha=alpha, **kwargs
        )

    def kde(self, ax=None, **kwargs) -> Axes:
        warnings.warn("kde is deprecated. Use plot.kde instead.", FutureWarning)

        return self.plot.kde(ax=ax, **kwargs)

    def plot_timeseries(
        self, title=None, *, ylim=None, figsize=None, backend="matplotlib", **kwargs
    ):
        warnings.warn(
            "plot_timeseries is deprecated. Use plot.timeseries instead.", FutureWarning
        )

        return self.plot.timeseries(
            title=title, ylim=ylim, figsize=figsize, backend=backend, **kwargs
        )

    def residual_hist(self, bins=100, title=None, color=None, **kwargs):
        warnings.warn(
            "residual_hist is deprecated. Use plot.residual_hist instead.",
            FutureWarning,
        )

        return self.plot.residual_hist(bins=bins, title=title, color=color, **kwargs)


# class PointComparer(Comparer):
#     pass


# class TrackComparer(Comparer):
#     pass
