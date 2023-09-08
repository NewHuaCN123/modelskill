from __future__ import annotations
from pathlib import Path
from typing import Optional, get_args
import mikeio
import pandas as pd

from ..utils import make_unique_index, _get_name
from ..types import Quantity, PointType
from ..timeseries import TimeSeries  # TODO move to main module


class PointModelResult(TimeSeries):
    """Construct a PointModelResult from a dfs0 file,
    mikeio.Dataset/DataArray or pandas.DataFrame/Series

    Parameters
    ----------
    data : types.UnstructuredType
        the input data or file path
    name : Optional[str], optional
        The name of the model result,
        by default None (will be set to file name or item name)
    x : float, optional
        first coordinate of point position, by default None
    y : float, optional
        second coordinate of point position, by default None
    item : str | int | None, optional
        If multiple items/arrays are present in the input an item
        must be given (as either an index or a string), by default None
    quantity : Quantity, optional
        Model quantity, for MIKE files this is inferred from the EUM information
    """

    def __init__(
        self,
        data: PointType,
        *,
        name: Optional[str] = None,  # TODO should maybe be required?
        x: Optional[float] = None,
        y: Optional[float] = None,
        item: str | int | None = None,
        quantity: Optional[Quantity] = None,
    ) -> None:
        assert isinstance(
            data, get_args(PointType)
        ), "Could not construct PointModelResult from provided data"

        if isinstance(data, (str, Path)):
            assert Path(data).suffix == ".dfs0", "File must be a dfs0 file"
            name = name or Path(data).stem
            data = mikeio.read(data)  # now mikeio.Dataset
        elif isinstance(data, mikeio.Dfs0):
            data = data.read()  # now mikeio.Dataset

        # parse item and convert to dataframe
        if isinstance(data, mikeio.Dataset):
            item_names = [i.name for i in data.items]
            item_name = _get_name(x=item, valid_names=item_names)
            df = data[[item_name]].to_dataframe()
        elif isinstance(data, mikeio.DataArray):
            if item is None:
                item_name = data.name
            df = data.to_dataframe()
        elif isinstance(data, pd.DataFrame):
            item_name = _get_name(x=item, valid_names=list(data.columns))
            df = data[[item_name]]
        elif isinstance(data, pd.Series):
            df = pd.DataFrame(data)  # to_frame?
            if item is None:
                item_name = df.columns[0]
        else:
            raise ValueError("Could not construct PointModelResult from provided data")

        name = name or item_name
        assert isinstance(name, str)

        # basic processing
        df = df.dropna()
        if df.empty or len(df.columns) == 0:
            raise ValueError("No data.")
        df.index = make_unique_index(df.index, offset_duplicates=0.001)

        model_quantity = Quantity.undefined() if quantity is None else quantity

        super().__init__(data=df, name=name, quantity=model_quantity)
        self.x = x
        self.y = y

        # self.gtype = GeometryType.POINT
