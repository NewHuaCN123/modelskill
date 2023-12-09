import pytest
import pandas as pd
import xarray as xr

import modelskill as ms


@pytest.fixture
def cc1():
    fn = "tests/testdata/NorthSeaHD_and_windspeed.dfsu"
    mr = ms.ModelResult(fn, item=0, name="HD")
    fn = "tests/testdata/altimetry_NorthSea_20171027.csv"
    df = pd.read_csv(fn, index_col=0, parse_dates=True)
    with pytest.warns(UserWarning, match="Removed 22 duplicate timestamps"):
        o1 = ms.TrackObservation(df, item=2, name="alti")

    return ms.compare(o1, mr)


@pytest.fixture
def o1():
    fn = "tests/testdata/SW/HKNA_Hm0.dfs0"
    return ms.PointObservation(fn, item=0, x=4.2420, y=52.6887, name="HKNA")


@pytest.fixture
def o2():
    fn = "tests/testdata/SW/eur_Hm0.dfs0"
    return ms.PointObservation(fn, item=0, x=3.2760, y=51.9990, name="EPL")


@pytest.fixture
def o3():
    fn = "tests/testdata/SW/Alti_c2_Dutch.dfs0"
    return ms.TrackObservation(fn, item=3, name="c2")


@pytest.fixture
def cc2(o1, o2, o3):
    fn = "tests/testdata/SW/DutchCoast_2017_subset.dfsu"
    mr1 = ms.ModelResult(fn, item=0, name="SW_1")
    fn = "tests/testdata/SW/DutchCoast_2017_subset.dfsu"
    mr2 = ms.ModelResult(fn, item=0, name="SW_2")

    return ms.compare([o1, o2, o3], [mr1, mr2])


def test_spatial_skill_deprecated(cc1):
    with pytest.warns(FutureWarning, match="gridded_skill"):
        ss = cc1.spatial_skill()
    assert isinstance(ss.data, xr.Dataset)
    assert len(ss.x) == 5
    assert len(ss.y) == 5
    assert len(ss.mod_names) == 0
    assert len(ss.obs_names) == 0
    df = ss.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert "Coordinates:" in repr(ss)
    assert ss.coords is not None
    assert ss.n is not None


def test_gridded_skill_multi_model(cc2):
    ss = cc2.gridded_skill(bins=3, metrics=["rmse", "bias"])
    assert len(ss.x) == 3
    assert len(ss.y) == 3
    assert len(ss.mod_names) == 2
    assert len(ss.obs_names) == 3
    assert len(ss.field_names) == 3


def test_gridded_skill_plot(cc1):
    ss = cc1.gridded_skill(metrics=["rmse", "bias"])
    ss.bias.plot()

    with pytest.warns(FutureWarning, match="deprecated"):
        ss.plot("bias")


def test_gridded_skill_plot_multi_model(cc2):
    ss = cc2.gridded_skill(by=["model"], metrics=["rmse", "bias"])
    ss["bias"].plot()

    ss.rmse.plot(model="SW_1")


def test_gridded_skill_plot_multi_model_fails(cc2):
    ss = cc2.gridded_skill(by=["model"], metrics=["rmse", "bias"])
    with pytest.raises(KeyError):
        ss["bad_metric"]

    with pytest.raises(ValueError):
        ss.rmse.plot(model="bad_model")
