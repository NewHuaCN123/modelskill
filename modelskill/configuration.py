import os
from pathlib import Path
import pandas as pd
import yaml
from typing import Union

from . import model_result, match
from .obs import PointObservation, TrackObservation
from .comparison import ComparerCollection


def from_config(
    conf: Union[dict, str, Path], *, relative_path=True
) -> ComparerCollection:
    """Load ComparerCollection from a config file (or dict)

    Parameters
    ----------
    conf : Union[str, Path, dict]
        path to config file or dict with configuration
    relative_path: bool, optional
        True: file paths are relative to configuration file,
        False: file paths are absolute (relative to the current directory),
        by default True

    Returns
    -------
    ComparerCollection
        A ComparerCollection object from the given configuration

    Examples
    --------
    >>> import modelskill as ms
    >>> cc = ms.from_config('Oresund.yml')
    """
    if isinstance(conf, (str, Path)):
        filename = str(conf)
        p = Path(conf)
        ext = p.suffix
        dirname = str(p.parents[0])
        if (ext == ".yml") or (ext == ".yaml") or (ext == ".conf"):
            conf = _yaml_to_dict(filename)
        elif "xls" in ext:
            conf = _excel_to_dict(filename)
        else:
            raise ValueError("Filename extension not supported! Use .yml or .xlsx")
    else:
        dirname = ""

    modelresults = {}

    assert isinstance(conf, dict)
    for name, mr_dict in conf["modelresults"].items():
        if not mr_dict.get("include", True):
            continue
        if relative_path:
            filename = os.path.join(dirname, mr_dict["filename"])
        else:
            filename = mr_dict["filename"]
        item = mr_dict.get("item")
        mr = model_result(filename, name=name, item=item)
        modelresults[name] = mr
    mr_list = list(modelresults.values())

    observations = {}
    for name, obs_dict in conf["observations"].items():
        if not obs_dict.get("include", True):
            continue
        if relative_path:
            filename = os.path.join(dirname, obs_dict["filename"])
        else:
            filename = obs_dict["filename"]
        item = obs_dict.get("item")
        alt_name = obs_dict.get("name")
        name = name if alt_name is None else alt_name

        otype = obs_dict.get("type")
        if (otype is not None) and ("track" in otype.lower()):
            obs = TrackObservation(filename, item=item, name=name)  # type: ignore
        else:
            x, y = obs_dict.get("x"), obs_dict.get("y")
            obs = PointObservation(filename, item=item, x=x, y=y, name=name)  # type: ignore
        observations[name] = obs
    obs_list = list(observations.values())

    # if "connections" in conf:
    #     raise NotImplementedError()
    return match(obs_list, mr_list)


def _yaml_to_dict(filename: str) -> dict:
    with open(filename) as f:
        contents = f.read()
    conf = yaml.load(contents, Loader=yaml.FullLoader)
    return conf


def _excel_to_dict(filename: str) -> dict:
    with pd.ExcelFile(filename, engine="openpyxl") as xls:
        dfmr = pd.read_excel(xls, "modelresults", index_col=0).T
        dfo = pd.read_excel(xls, "observations", index_col=0).T
        # try: dfc = pd.read_excel(xls, "connections", index_col=0).T
    conf = {}
    conf["modelresults"] = _remove_keys_w_nan_value(dfmr.to_dict())
    conf["observations"] = _remove_keys_w_nan_value(dfo.to_dict())
    return conf


def _remove_keys_w_nan_value(d: dict) -> dict:
    """Loops through dicts in dict and removes all entries where value is NaN
    e.g. x,y values of TrackObservations
    """
    dout = {}
    for key, subdict in d.items():
        dout[key] = {k: v for k, v in subdict.items() if pd.Series(v).notna().all()}
    return dout
