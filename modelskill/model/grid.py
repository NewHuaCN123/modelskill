from __future__ import annotations
from pathlib import Path
from typing import Optional, Sequence, get_args
import warnings

import pandas as pd
import xarray as xr

from ..utils import get_item_name_and_idx, rename_coords_xr, rename_coords_pd
from ..types import GridType, Quantity
from .point import PointModelResult
from .track import TrackModelResult
from ..observation import Observation, PointObservation, TrackObservation


class GridModelResult:
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
    """

    def __init__(
        self,
        data: GridType,
        *,
        name: Optional[str] = None,
        item: str | int | None = None,
        quantity: Optional[Quantity] = None,
    ) -> None:
        assert isinstance(
            data, get_args(GridType)
        ), "Could not construct GridModelResult from provided data."

        if isinstance(data, (str, Path)):
            if "*" in str(data):
                data = xr.open_mfdataset(data)
            else:
                assert Path(data).exists(), f"{data}: File does not exist."
                data = xr.open_dataset(data)

        elif isinstance(data, Sequence) and all(
            isinstance(file, (str, Path)) for file in data
        ):
            data = xr.open_mfdataset(data)

        elif isinstance(data, xr.DataArray):
            assert data.ndim >= 2, "DataArray must at least 2D."
            data = data.to_dataset(name=name, promote_attrs=True)
        elif isinstance(data, xr.Dataset):
            assert len(data.coords) >= 2, "Dataset must have at least 2 dimensions."

        else:
            raise NotImplementedError(
                f"Could not construct GridModelResult from {type(data)}"
            )

        item_name, _ = get_item_name_and_idx(list(data.data_vars), item)
        name = name or item_name
        data = rename_coords_xr(data)

        self.data = data[item_name]
        self.name = name
        self.quantity = quantity or Quantity.undefined()

    # TODO reconsider this function (signature copied from _base)
    def _validate_any_obs_in_model_time(
        self, obs_name: str, time_obs: pd.DatetimeIndex, time_model: pd.DatetimeIndex
    ) -> None:
        pass

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
        overlap_in_time = (
            self.time[0] <= observation.time[-1]
            and self.time[-1] >= observation.time[0]
        )
        if not overlap_in_time:
            warnings.warn(
                f"No time overlap. Observation '{observation.name}' outside model time range! "
            )
        if isinstance(observation, PointObservation):
            return self._extract_point(observation)
        elif isinstance(observation, TrackObservation):
            return self._extract_track(observation)
        else:
            raise NotImplementedError(
                f"Extraction from {type(self.data)} to {type(observation)} is not implemented."
            )

    def _extract_point(self, observation: PointObservation) -> PointModelResult:
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

        self._validate_any_obs_in_model_time(
            observation.name, observation.data.index, self.time
        )
        # TODO add correct type hint to self.data
        assert isinstance(self.data, xr.DataArray)

        # TODO self.item is None, ☹️
        da = self.data.interp(coords=dict(x=x, y=y), method="nearest")  # type: ignore
        df = da.to_dataframe().drop(columns=["x", "y"])
        df = df.rename(columns={df.columns[-1]: self.name})

        return PointModelResult(
            data=df.dropna(),
            x=da.x.item(),
            y=da.y.item(),
            item=self.name,
            name=self.name,
            quantity=self.quantity,
        )

    def _extract_track(self, observation: TrackObservation) -> TrackModelResult:
        """Extract a TrackModelResult from a GridModelResult (when data is a xarray.Dataset),
        given a TrackObservation."""

        self._validate_any_obs_in_model_time(
            observation.name, observation.data.index, self.time
        )

        renamed_obs_data = rename_coords_pd(observation.data)
        t = xr.DataArray(renamed_obs_data.index, dims="track")
        x = xr.DataArray(renamed_obs_data.x, dims="track")
        y = xr.DataArray(renamed_obs_data.y, dims="track")

        assert isinstance(self.data, xr.DataArray)
        da = self.data.interp(coords=dict(time=t, x=x, y=y), method="linear")
        df = da.to_dataframe().drop(columns=["time"])
        df = df.rename(columns={df.columns[-1]: self.name})

        return TrackModelResult(
            data=df.dropna(),
            item=self.name,
            name=self.name,
            quantity=self.quantity,
        )
