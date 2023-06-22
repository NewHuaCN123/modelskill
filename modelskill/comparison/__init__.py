"""The `comparison` module contains different types of comparer classes for
fixed locations (PointComparer), or locations moving in space (TrackComparer).
"""

from ._comparison import Comparer, PointComparer, TrackComparer, ComparerCollection

__all__ = ["Comparer", "PointComparer", "TrackComparer", "ComparerCollection"]
