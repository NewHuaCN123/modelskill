# from typing import List, Optional, Union


# def _get_name(x: Optional[Union[str, int]], valid_names: List[str]) -> str:
#     """Parse name/id from list of valid names (e.g. obs from obs_names), return name"""
#     return valid_names[_get_idx(x, valid_names)]


# def _get_idx(x: Optional[Union[str, int]], valid_names: List[str]) -> int:
#     """Parse name/id from list of valid names (e.g. obs from obs_names), return id"""
#     n = len(valid_names)
#     if n == 0:
#         raise ValueError(f"Cannot select {x} from empty list!")
#     if x is None:
#         return 0  # default to first
#     elif isinstance(x, str):
#         if x in valid_names:
#             idx = valid_names.index(x)
#         else:
#             raise KeyError(f"Name {x} could not be found in {valid_names}")
#     elif isinstance(x, int):
#         if x < 0:  # Handle negative indices
#             x += n
#         if x >= 0 and x < n:
#             idx = x
#         else:
#             raise IndexError(f"Id {x} is out of range for {valid_names}")
#     else:
#         raise TypeError(f"Input {x} invalid! Must be None, str or int, not {type(x)}")
#     return idx
