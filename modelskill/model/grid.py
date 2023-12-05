from __future__ import annotations
from pathlib import Path
from typing import Optional, Sequence, get_args

import pandas as pd
import xarray as xr

from ._base import SpatialField, _validate_overlap_in_time, _parse_items, SelectedItems
from ..utils import _get_name, rename_coords_xr, rename_coords_pd
from ..types import GridType, Quantity
from .point import PointModelResult
from .track import TrackModelResult
from ..observation import Observation, PointObservation, TrackObservation


class GridModelResult(SpatialField):
    """Construct a GridModelResult from a file or xarray.Dataset.

    Parameters
    ----------
    data : types.GridType
        the input data or file path
    name : str, optional
        The name of the model result,
        by default None (will be set to file name or item name)
    item : str or int, optional
        If multiple items/arrays are present in the input an item
        must be given (as either an index or a string), by default None
    quantity : Quantity, optional
        Model quantity, for MIKE files this is inferred from the EUM information
    aux_items : Optional[list[int | str]], optional
        Auxiliary items, by default None
    """

    def __init__(
        self,
        data: GridType,
        *,
        name: Optional[str] = None,
        item: str | int | None = None,
        quantity: Optional[Quantity] = None,
        aux_items: Optional[list[int | str]] = None,
    ) -> None:
        assert isinstance(
            data, get_args(GridType)
        ), "Could not construct GridModelResult from provided data."

        if isinstance(data, (str, Path)):
            if "*" in str(data):
                ds = xr.open_mfdataset(data)
            else:
                assert Path(data).exists(), f"{data}: File does not exist."
                ds = xr.open_dataset(data)

        elif isinstance(data, Sequence) and all(
            isinstance(file, (str, Path)) for file in data
        ):
            ds = xr.open_mfdataset(data)

        elif isinstance(data, xr.DataArray):
            if item is not None:
                raise ValueError(f"item must be None when data is a {type(data)}")
            if aux_items is not None:
                raise ValueError(f"aux_items must be None when data is a {type(data)}")
            if data.ndim < 2:
                raise ValueError(f"DataArray must at least 2D. Got {list(data.dims)}.")
            ds = data.to_dataset(name=name, promote_attrs=True)
        elif isinstance(data, xr.Dataset):
            assert len(data.coords) >= 2, "Dataset must have at least 2 dimensions."
            ds = data
        else:
            raise NotImplementedError(
                f"Could not construct GridModelResult from {type(data)}"
            )

        sel_items = _parse_items(list(ds.data_vars), item=item, aux_items=aux_items)
        # item_names = [_get_name(x=item, valid_names=list(ds.data_vars))]
        # if aux_items is not None:
        #     item_names.extend(
        #         [
        #             _get_name(x=item, valid_names=list(ds.data_vars))
        #             for item in aux_items
        #         ]
        #     )
        #     if len(set(item_names)) != len(item_names):
        #         raise ValueError(
        #             f"Duplicate item names in {item_names}. Please provide unique names."
        #         )
        name = name or sel_items.values
        ds = rename_coords_xr(ds)

        self.data: xr.Dataset = ds[sel_items.all]
        self.name = name

        # use long_name and units from data if not provided
        if quantity is None:
            # TODO: should this be on the DataArray instead?
            if self.data.attrs.get("long_name") and self.data.attrs.get("units"):
                quantity = Quantity(
                    name=self.data.attrs["long_name"],
                    unit=self.data.attrs["units"],
                )
            else:
                quantity = Quantity.undefined()

        self.quantity = quantity

    @property
    def time(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.data.time)

    @property
    def start_time(self) -> pd.Timestamp:
        return self.time[0]

    @property
    def end_time(self) -> pd.Timestamp:
        return self.time[-1]

    def _in_domain(self, x: float, y: float) -> bool:
        assert hasattr(self.data, "x") and hasattr(
            self.data, "y"
        ), "Data has no x and/or y coordinates."
        xmin = self.data.x.values.min()
        xmax = self.data.x.values.max()
        ymin = self.data.y.values.min()
        ymax = self.data.y.values.max()
        return (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)

    def extract(self, observation: Observation) -> PointModelResult | TrackModelResult:
        """Extract ModelResult at observation positions

        Parameters
        ----------
        observation : <PointObservation> or <TrackObservation>
            positions (and times) at which modelresult should be extracted

        Returns
        -------
        <modelskill.protocols.Comparable>
            A model result object with the same geometry as the observation
        """
        _validate_overlap_in_time(self.time, observation)
        if isinstance(observation, PointObservation):
            return self.extract_point(observation)
        elif isinstance(observation, TrackObservation):
            return self.extract_track(observation)
        else:
            raise NotImplementedError(
                f"Extraction from {type(self.data)} to {type(observation)} is not implemented."
            )

    def extract_point(self, observation: PointObservation) -> PointModelResult:
        """Spatially extract a PointModelResult from a GridModelResult (when data is a xarray.Dataset),
        given a PointObservation. No time interpolation is done!"""

        x, y = observation.x, observation.y
        if (x is None) or (y is None):
            raise ValueError(
                f"PointObservation '{observation.name}' cannot be used for extraction "
                + f"because it has None position x={x}, y={y}. Please provide position "
                + "when creating PointObservation."
            )
        if not self._in_domain(x, y):
            raise ValueError(
                f"PointObservation '{observation.name}' ({x}, {y}) is outside model domain!"
            )

        # TODO add correct type hint to self.data
        assert isinstance(self.data, xr.Dataset)

        # TODO: avoid runtrip to pandas if possible (potential loss of metadata)
        da = self.data.interp(coords=dict(x=x, y=y), method="nearest")  # type: ignore
        df = da.to_dataframe().drop(columns=["x", "y"])
        df = df.rename(columns={list(da.data_vars)[0]: self.name})

        return PointModelResult(
            data=df.dropna(),
            x=da.x.item(),
            y=da.y.item(),
            item=self.name,
            name=self.name,
            quantity=self.quantity,
            # aux_items=self.aux_items, ?
        )

    def extract_track(self, observation: TrackObservation) -> TrackModelResult:
        """Extract a TrackModelResult from a GridModelResult (when data is a xarray.Dataset),
        given a TrackObservation."""

        obs_df = observation.data.to_dataframe()

        renamed_obs_data = rename_coords_pd(obs_df)
        t = xr.DataArray(renamed_obs_data.index, dims="track")
        x = xr.DataArray(renamed_obs_data.x, dims="track")
        y = xr.DataArray(renamed_obs_data.y, dims="track")

        assert isinstance(self.data, xr.Dataset)
        da = self.data.interp(coords=dict(time=t, x=x, y=y), method="linear")
        df = da.to_dataframe().drop(columns=["time"])
        df = df.rename(columns={list(da.data_vars)[0]: self.name})

        return TrackModelResult(
            data=df.dropna(),
            item=self.name,
            x_item="x",
            y_item="y",
            name=self.name,
            quantity=self.quantity,
            # aux_items=self.aux_items, ?
        )
