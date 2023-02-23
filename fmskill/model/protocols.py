from typing import Any, Optional, Protocol, Union, runtime_checkable

import pandas as pd


@runtime_checkable
class ModelResult(Protocol):
    data: Any
    item: str
    name: str
    quantity: str


@runtime_checkable
class Observation(Protocol):
    data: pd.DataFrame
    name: str


@runtime_checkable
class PointObject(Protocol):

    x: float
    y: float


@runtime_checkable
class PointObservation(PointObject, Observation, Protocol):
    ...


@runtime_checkable
class Comparable(ModelResult, Protocol):

    data: pd.DataFrame

    def compare(self, observation: Union[PointObservation, Observation]):
        # assert isinstance(self.data, ExtractableType), "data is not extractable"
        ...


@runtime_checkable
class Extractable(ModelResult, Protocol):

    # Declaring data as Any, because mikeio.open() returns some possible types
    # that we currently don't handle. Instead checking for proper type in extract()
    data: Any

    def extract(
        self, observation: Union[PointObservation, Observation]
    ) -> Optional[Comparable]:
        ...


@runtime_checkable
class PointModelResult(PointObject, Comparable, Protocol):
    ...
