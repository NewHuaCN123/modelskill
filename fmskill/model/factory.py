from pathlib import Path
from typing import Literal, Optional

import pandas as pd
import xarray as xr

from fmskill import model
from fmskill.model import protocols
from fmskill.types import GeometryType, DataInputType

modelresult_lookup = {
    GeometryType.POINT: model.PointModelResult,
    GeometryType.TRACK: model.TrackModelResult,
    GeometryType.UNSTRUCTURED: model.DfsuModelResult,
    GeometryType.GRID: model.GridModelResult,
}


class ModelResult:
    def __new__(
        cls,
        data: DataInputType,
        *,
        gtype: Optional[Literal["point", "track", "unstructured", "grid"]] = None,
        **kwargs,
    ) -> protocols.ModelResult:
        if gtype is None:
            geometry = cls._guess_gtype(data)
        else:
            geometry = GeometryType.from_string(gtype)

        return modelresult_lookup[geometry](
            data=data,
            **kwargs,
        )

    @staticmethod
    def _guess_gtype(data) -> GeometryType:

        if hasattr(data, "geometry"):
            geom_str = repr(data.geometry).lower()
            if "flex" in geom_str:
                return GeometryType.UNSTRUCTURED
            elif "point" in geom_str:
                return GeometryType.POINT
            else:
                raise ValueError(
                    "Could not guess gtype from geometry, please specify gtype, e.g. gtype='track'"
                )

        if isinstance(data, (str, Path)):
            data = Path(data)
            file_ext = data.suffix.lower()
            if file_ext == ".dfsu":
                return GeometryType.UNSTRUCTURED
            elif file_ext == ".dfs0":
                # could also be a track, but we don't know
                return GeometryType.POINT
            elif file_ext == ".nc":
                # could also be point or track, but we don't know
                return GeometryType.GRID
            else:
                raise ValueError(
                    "Could not guess gtype from file extension, please specify gtype, e.g. gtype='track'"
                )

        if isinstance(data, (xr.Dataset, xr.DataArray)):
            if len(data.coords) >= 3:
                # if DataArray use ndim instead
                return GeometryType.GRID
            else:
                raise ValueError("Could not guess gtype from xarray object")
        if isinstance(data, (pd.DataFrame, pd.Series)):
            # could also be a track, but we don't know
            return GeometryType.POINT

        raise ValueError(
            f"Geometry type (gtype) could not be guessed from this type of data: {type(data)}. Please specify gtype, e.g. gtype='track'"
        )
