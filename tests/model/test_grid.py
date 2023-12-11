from datetime import datetime
import pytest
import xarray as xr
import pandas as pd

import modelskill as ms


@pytest.fixture
def ERA5_DutchCoast_nc():
    return "tests/testdata/SW/ERA5_DutchCoast.nc"


@pytest.fixture
def mr_ERA5_pp1d(ERA5_DutchCoast_nc):
    return ms.model_result(ERA5_DutchCoast_nc, name="ERA5_DutchCoast", item="pp1d")


@pytest.fixture
def mr_ERA5_swh(ERA5_DutchCoast_nc):
    return ms.model_result(ERA5_DutchCoast_nc, name="ERA5_DutchCoast", item="swh")


@pytest.fixture
def mf_modelresult():
    fn = "tests/testdata/SW/CMEMS_DutchCoast_*.nc"
    return ms.model_result(fn, item="VHM0", name="CMEMS")


@pytest.fixture
def pointobs_epl_hm0():
    return ms.PointObservation(
        "tests/testdata/SW/eur_Hm0.dfs0", item=0, x=3.2760, y=51.9990, name="EPL"
    )


@pytest.fixture
def trackobs_c2_hm0():
    return ms.TrackObservation(
        "tests/testdata/SW/Alti_c2_Dutch.dfs0", item=3, name="c2"
    )


def test_grid_from_nc(mr_ERA5_pp1d):
    mr = mr_ERA5_pp1d
    assert mr.name == "ERA5_DutchCoast"
    assert mr.start_time == datetime(2017, 10, 27, 0, 0, 0)
    assert mr.end_time == datetime(2017, 10, 29, 18, 0, 0)


def test_grid_from_DataArray(ERA5_DutchCoast_nc):
    ds = xr.open_dataset(ERA5_DutchCoast_nc)
    mr = ms.GridModelResult(ds["swh"])
    assert mr.quantity.name == "Significant height of combined wind waves and swell"
    assert mr.quantity.unit == "m"

    mr2 = ms.GridModelResult(
        ds["swh"], quantity=ms.Quantity("Significant height", unit="meter")
    )
    assert mr2.quantity.name == "Significant height"
    assert mr2.quantity.unit == "meter"


def test_dataset_with_missing_coordinates(ERA5_DutchCoast_nc):
    ds = xr.open_dataset(ERA5_DutchCoast_nc)
    ds = ds.drop_vars(["longitude"])  # remove one of the coordinates

    with pytest.raises(ValueError, match="gtype"):
        ms.model_result(ds["swh"])


def test_grid_from_da(ERA5_DutchCoast_nc):
    ds = xr.open_dataset(ERA5_DutchCoast_nc)
    da = ds["swh"]
    mr = ms.model_result(da)

    assert isinstance(mr, ms.GridModelResult)
    # assert not mr.filename


def test_grid_from_multifile(mf_modelresult):
    mr = mf_modelresult

    assert mr.name == "CMEMS"
    assert mr.start_time == datetime(2017, 10, 28, 0, 0, 0)
    assert mr.end_time == datetime(2017, 10, 29, 18, 0, 0)


# should be supported
def test_grid_name(ERA5_DutchCoast_nc):
    mri1 = ms.model_result(ERA5_DutchCoast_nc, item="pp1d")
    assert isinstance(mri1, ms.GridModelResult)

    mri2 = ms.model_result(ERA5_DutchCoast_nc, item=3)
    assert isinstance(mri2, ms.GridModelResult)

    assert mri1.name == mri2.name


def test_grid_aux_items(ERA5_DutchCoast_nc):
    mr = ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items=["swh"])
    assert mr.sel_items.values == "pp1d"
    assert mr.sel_items.aux == ["swh"]
    assert list(mr.data.data_vars) == ["pp1d", "swh"]

    mr = ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items=["swh", "mwp"])
    assert mr.sel_items.values == "pp1d"
    assert mr.sel_items.aux == ["swh", "mwp"]
    assert list(mr.data.data_vars) == ["pp1d", "swh", "mwp"]

    # accept string instead of list
    mr = ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items="swh")
    assert mr.sel_items.values == "pp1d"
    assert mr.sel_items.aux == ["swh"]
    assert list(mr.data.data_vars) == ["pp1d", "swh"]

    # use index instead of name
    mr = ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items=[4, 1])
    assert mr.sel_items.values == "pp1d"
    assert mr.sel_items.aux == ["swh", "mwp"]
    assert list(mr.data.data_vars) == ["pp1d", "swh", "mwp"]


def test_grid_aux_items_fail(ERA5_DutchCoast_nc):
    with pytest.raises(ValueError, match="Duplicate items"):
        ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items=["swh", "pp1d"])

    with pytest.raises(ValueError, match="Duplicate items"):
        ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items=["swh", "swh"])


# def test_grid_itemInfo(ERA5_DutchCoast_nc):
#     mri1 = ModelResult(ERA5_DutchCoast_nc, item="pp1d")
#     assert mri1.itemInfo == mikeio.ItemInfo(mikeio.EUMType.Undefined)

#     itemInfo = mikeio.EUMType.Wave_period
#     mri3 = ModelResult(ERA5_DutchCoast_nc, item="pp1d", itemInfo=itemInfo)
#     mri3.itemInfo == mikeio.ItemInfo(mikeio.EUMType.Wave_period)

#     itemInfo = mikeio.ItemInfo("Peak period", mikeio.EUMType.Wave_period)
#     mri3 = ModelResult(ERA5_DutchCoast_nc, item="pp1d", itemInfo=itemInfo)
#     mri3.itemInfo == mikeio.ItemInfo("Peak period", mikeio.EUMType.Wave_period)


def test_grid_extract_point(mr_ERA5_swh, pointobs_epl_hm0):
    pmr = mr_ERA5_swh.extract(pointobs_epl_hm0)
    ds = pmr.data

    assert isinstance(pmr, ms.PointModelResult)
    assert pmr.start_time == datetime(2017, 10, 27, 0, 0, 0)
    assert pmr.end_time == datetime(2017, 10, 29, 18, 0, 0)
    assert pmr.n_points == 67
    assert len(ds.data_vars) == 1
    assert pytest.approx(ds.to_pandas().iloc[0, 0]) == 0.875528


def test_grid_extract_point_xoutside(mr_ERA5_pp1d, pointobs_epl_hm0):
    mri = mr_ERA5_pp1d
    pointobs_epl_hm0.x = -50
    with pytest.raises(ValueError, match="outside"):
        mri.extract(pointobs_epl_hm0)


def test_grid_extract_point_toutside(ERA5_DutchCoast_nc, pointobs_epl_hm0):
    ds = xr.open_dataset(ERA5_DutchCoast_nc)
    da = ds["swh"].isel(time=slice(10, 15))
    da["time"] = pd.Timedelta("365D") + da.time
    mr = ms.GridModelResult(da)
    with pytest.warns(UserWarning, match="outside"):
        mr.extract(pointobs_epl_hm0)


def test_grid_extract_point_aux(ERA5_DutchCoast_nc, pointobs_epl_hm0):
    mr = ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items=["swh"])
    pc = mr.extract(pointobs_epl_hm0)
    assert isinstance(pc, ms.PointModelResult)
    assert pc.start_time == datetime(2017, 10, 27, 0, 0, 0)
    assert pc.end_time == datetime(2017, 10, 29, 18, 0, 0)
    assert pc.n_points == 67
    assert len(pc.data.data_vars) == 2


@pytest.mark.skip(
    reason="validation not possible at the moment, allow item mapping for ModelResult and Observation and match on item name?"
)
def test_grid_extract_point_wrongitem(mr_ERA5_pp1d, pointobs_epl_hm0):
    mri = mr_ERA5_pp1d
    pc = mri.extract(pointobs_epl_hm0)
    assert pc is None


def test_grid_extract_track(mr_ERA5_pp1d, trackobs_c2_hm0):
    mri = mr_ERA5_pp1d
    tmr = mri.extract(trackobs_c2_hm0)
    assert isinstance(tmr, ms.TrackModelResult)
    assert tmr.start_time.replace(microsecond=0) == datetime(2017, 10, 27, 12, 52, 52)
    assert tmr.end_time.replace(microsecond=0) == datetime(2017, 10, 29, 12, 51, 28)
    assert tmr.n_points == 99


def test_grid_extract_track_aux(ERA5_DutchCoast_nc, trackobs_c2_hm0):
    mr = ms.GridModelResult(ERA5_DutchCoast_nc, item="pp1d", aux_items=["swh"])
    tc = mr.extract(trackobs_c2_hm0)
    assert isinstance(tc, ms.TrackModelResult)
    assert tc.start_time.replace(microsecond=0) == datetime(2017, 10, 27, 12, 52, 52)
    assert tc.end_time.replace(microsecond=0) == datetime(2017, 10, 29, 12, 51, 28)
    assert tc.n_points == 99
    assert len(tc.data.data_vars) == 2
    assert "swh" in tc.data.data_vars
