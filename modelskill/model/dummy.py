from __future__ import annotations
from typing import Literal

import pandas as pd

from modelskill.model.point import PointModelResult
from modelskill.model.track import TrackModelResult
from modelskill.obs import PointObservation, TrackObservation


class DummyModelResult:
    """Dummy model result that always returns the same value.

    Similar in spirit to <https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyRegressor.html>

    Parameters
    ----------
    data : float, optional
        The value to return if strategy is 'constant', by default None
    name : str, optional
        The name of the model result, by default "dummy"
    """

    def __init__(
        self,
        data: float | None = None,
        *,
        name: str = "dummy",
        strategy: Literal["mean", "constant"] = "constant",
    ):
        if strategy == "constant":
            if data is None:
                raise ValueError("data must be given when strategy is 'constant'")
        self.data = data
        self.name = name
        self.strategy = strategy

    def extract(
        self, observation: PointObservation | TrackObservation
    ) -> PointModelResult | TrackModelResult:
        if isinstance(observation, PointObservation):
            da = observation.data[observation.name].copy()
            if self.strategy == "mean":
                da[:] = da.mean()
            else:
                da[:] = self.data
            pmr = PointModelResult(
                data=da, x=observation.x, y=observation.y, name=self.name
            )
            return pmr

        if isinstance(observation, TrackObservation):
            da = observation.data[observation.name].copy()
            if self.strategy == "mean":
                da[:] = da.mean()
            else:
                da[:] = self.data

            data = pd.DataFrame(
                {
                    "x": observation.x,
                    "y": observation.y,
                    "value": da.values,
                },
                index=da.time,
            )
            tmr = TrackModelResult(data=data, name=self.name)
            return tmr
