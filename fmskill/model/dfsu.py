from pathlib import Path
from typing import Callable, Mapping, Optional, Union, get_args
import warnings

import mikeio
import numpy as np
import pandas as pd

from fmskill import types, utils
from fmskill.model import protocols
from fmskill.model._base import ModelResultBase
from fmskill.model.point import PointModelResult
from fmskill.model.track import TrackModelResult
from fmskill.observation import Observation, PointObservation, TrackObservation


class DfsuModelResult(ModelResultBase):
    def __init__(
        self,
        data: types.UnstructuredType,
        *,
        name: Optional[str] = None,
        item: Optional[Union[str, int]] = None,
        itemInfo=None,
        quantity: Optional[str] = None,
    ) -> None:
        name = name or super()._default_name(data)

        assert isinstance(
            data, get_args(types.UnstructuredType)
        ), "Could not construct DfsuModelResult from provided data"

        filename = None
        if isinstance(data, (str, Path)):
            assert Path(data).suffix == ".dfsu", "File must be a dfsu file"
            filename = str(data)
            data = mikeio.open(data)

        elif isinstance(data, (mikeio.DataArray, mikeio.Dataset)):
            if not isinstance(data.geometry, mikeio.spatial.FM_geometry.GeometryFM):
                raise ValueError(f"Geometry of {type(data)} is not supported.")
        else:
            raise ValueError(
                f"data type must be .dfsu or dfsu-Dataset/DataArray. Not {type(data)}."
            )

        if isinstance(data, mikeio.DataArray):
            if isinstance(item, int):
                raise ValueError("item must be a string when data is a DataArray")
            item_name = item or data.name
            itemInfo = itemInfo or data.item
        else:
            item_names = [i.name for i in data.items]
            item_name, idx = utils.get_item_name_and_idx(item_names, item)
            itemInfo = itemInfo or data.items[idx]

        name = name or item_name

        super().__init__(
            data=data, name=name, item=item_name, itemInfo=itemInfo, quantity=quantity
        )

        self.filename = filename  # TODO: remove? backward compatibility

    # def _in_domain(self, x, y) -> bool:
    #    return self.data.geometry.contains([x, y])

    @staticmethod
    def _any_obs_in_model_time(
        time_obs: pd.DatetimeIndex, time_model: pd.DatetimeIndex
    ) -> bool:
        """Check if any observation times are in model time range"""
        return (time_obs[-1] >= time_model[0]) & (time_obs[0] <= time_model[-1])

    def _validate_any_obs_in_model_time(
        self, obs_name: str, time_obs: pd.DatetimeIndex, time_model: pd.DatetimeIndex
    ) -> None:
        """Check if any observation times are in model time range"""
        ok = self._any_obs_in_model_time(time_obs, time_model)
        if not ok:
            # raise ValueError(
            warnings.warn(
                f"No time overlap. Observation '{obs_name}' outside model time range! "
                + f"({time_obs[0]} - {time_obs[-1]}) not in ({time_model[0]} - {time_model[-1]})"
            )

    def extract(self, observation: Observation) -> protocols.Comparable:
        extractor_lookup: Mapping[Observation, Callable] = {
            PointObservation: self._extract_point,
            TrackObservation: self._extract_track,
        }
        extraction_func = extractor_lookup.get(type(observation))
        if extraction_func is None:
            raise NotImplementedError(
                f"Extraction from {type(self.data)} to {type(observation)} is not implemented."
            )
        return extraction_func(observation)

    def _extract_point(self, observation: PointObservation) -> PointModelResult:
        """Spatially extract a PointModelResult from a DfsuModelResult (when data is a Dfsu object),
        given a PointObservation. No time interpolation is done!"""

        assert isinstance(
            self.data, (mikeio.dfsu.Dfsu2DH, mikeio.DataArray, mikeio.Dataset)
        )

        x, y = observation.x, observation.y
        if not self.data.geometry.contains([x, y]):
            raise ValueError(
                f"PointObservation '{observation.name}' ({x}, {y}) outside model domain!"
            )

        self._validate_any_obs_in_model_time(
            observation.name, observation.data.index, self.time
        )

        # TODO: interp2d
        xy = np.atleast_2d([x, y])
        elemids = self.data.geometry.find_index(coords=xy)
        if isinstance(self.data, mikeio.dfsu.Dfsu2DH):
            ds_model = self.data.read(elements=elemids, items=[self.item])
        elif isinstance(self.data, mikeio.Dataset):
            ds_model = self.data.isel(element=elemids)
        elif isinstance(self.data, mikeio.DataArray):
            da = self.data.isel(element=elemids)
            ds_model = mikeio.Dataset({da.name: da})
        ds_model.rename({ds_model.items[0].name: self.name}, inplace=True)

        return PointModelResult(
            data=ds_model,
            x=ds_model.geometry.x,
            y=ds_model.geometry.y,
            item=self.name,
            itemInfo=self.itemInfo,
            name=self.name,
            quantity=self.quantity,
        )

    def _extract_track(self, observation: TrackObservation) -> TrackModelResult:
        """Extract a TrackModelResult from a DfsuModelResult (when data is a Dfsu object),
        given a TrackObservation."""

        assert isinstance(
            self.data, (mikeio.dfsu.Dfsu2DH, mikeio.DataArray, mikeio.Dataset)
        )

        self._validate_any_obs_in_model_time(
            observation.name, observation.data.index, self.time
        )

        if isinstance(self.data, mikeio.dfsu.Dfsu2DH):
            ds_model = self.data.extract_track(
                track=observation.data, items=[self.item]
            )
        elif isinstance(self.data, (mikeio.Dataset, mikeio.DataArray)):
            ds_model = self.data.extract_track(track=observation.data)
        ds_model.rename({ds_model.items[-1].name: self.name}, inplace=True)

        return TrackModelResult(
            data=ds_model.dropna(),  # .to_dataframe().dropna(),
            item=self.name,
            itemInfo=self.itemInfo,
            name=self.name,
            quantity=self.quantity,
        )
