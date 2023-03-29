import numpy as np
import pytest
import pandas as pd
import xarray as xr
import fmskill.comparison


def _get_df() -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "Observation": [1.0, 2.0, 3.0, 4.0, 5.0, np.nan],
            "x": [10.1, 10.2, 10.3, 10.4, 10.5, 10.6],
            "y": [55.1, 55.2, 55.3, 55.4, 55.5, 55.6],
            "m1": [1.5, 2.4, 3.6, 4.9, 5.6, 6.4],
            "m2": [1.1, 2.2, 3.1, 4.2, 4.9, 6.2],
        },
        index=pd.date_range("2019-01-01", periods=6, freq="D"),
    )
    df.index.name = "time"
    return df


def _set_attrs(data: xr.Dataset) -> xr.Dataset:
    data.attrs["variable_name"] = "fake var"
    data["x"].attrs["kind"] = "position"
    data["y"].attrs["kind"] = "position"
    data["Observation"].attrs["kind"] = "observation"
    data["Observation"].attrs["weight"] = 1.0
    data["Observation"].attrs["unit"] = "m"
    data["m1"].attrs["kind"] = "model"
    data["m2"].attrs["kind"] = "model"
    return data


@pytest.fixture
def pc() -> fmskill.comparison.Comparer:
    """A comparer with fake point data"""
    x, y = 10.0, 55.0
    df = _get_df().drop(columns=["x", "y"])
    raw_data = {"m1": df[["m1"]], "m2": df[["m2"]]}

    data = df.dropna().to_xarray()
    data.attrs["gtype"] = "point"
    data.attrs["name"] = "fake point obs"
    data["x"] = x
    data["y"] = y
    data = _set_attrs(data)
    return fmskill.comparison.Comparer(matched_data=data, raw_mod_data=raw_data)


@pytest.fixture
def tc() -> fmskill.comparison.Comparer:
    """A comparer with fake track data"""
    df = _get_df()
    raw_data = {"m1": df[["x", "y", "m1"]], "m2": df[["x", "y", "m2"]]}

    data = df.dropna().to_xarray()
    data.attrs["gtype"] = "track"
    data.attrs["name"] = "fake track obs"
    data = _set_attrs(data)

    return fmskill.comparison.Comparer(matched_data=data, raw_mod_data=raw_data)


def test_pc_properties(pc):
    assert pc.n_models == 2
    assert pc.n_points == 5
    assert pc.gtype == "point"
    assert pc.x == 10.0
    assert pc.y == 55.0
    assert pc.name == "fake point obs"
    assert pc.variable_name == "fake var"
    assert pc.start == pd.Timestamp("2019-01-01")
    assert pc.end == pd.Timestamp("2019-01-05")
    assert pc.mod_names == ["m1", "m2"]
    assert pc.obs[-1] == 5.0
    assert pc.mod[-1, 1] == 4.9

    assert pc.raw_mod_data["m1"].columns.tolist() == ["m1"]
    assert np.all(pc.raw_mod_data["m1"]["m1"] == [1.5, 2.4, 3.6, 4.9, 5.6, 6.4])


def test_tc_properties(tc):
    assert tc.n_models == 2
    assert tc.n_points == 5
    assert tc.gtype == "track"
    assert np.all(tc.x == [10.1, 10.2, 10.3, 10.4, 10.5])
    assert np.all(tc.y == [55.1, 55.2, 55.3, 55.4, 55.5])
    assert tc.name == "fake track obs"
    assert tc.variable_name == "fake var"
    assert tc.start == pd.Timestamp("2019-01-01")
    assert tc.end == pd.Timestamp("2019-01-05")
    assert tc.mod_names == ["m1", "m2"]
    assert tc.obs[-1] == 5.0
    assert tc.mod[-1, 1] == 4.9

    assert tc.raw_mod_data["m1"].columns.tolist() == ["x", "y", "m1"]
    assert np.all(tc.raw_mod_data["m1"]["m1"] == [1.5, 2.4, 3.6, 4.9, 5.6, 6.4])
    assert np.all(tc.raw_mod_data["m1"]["x"] == [10.1, 10.2, 10.3, 10.4, 10.5, 10.6])


def test_pc_sel_time(pc):
    pc2 = pc.sel(time=slice("2019-01-03", "2019-01-04"))
    assert pc2.n_points == 2
    assert pc2.data.Observation.values.tolist() == [3.0, 4.0]


def test_pc_sel_time_empty(pc):
    pc2 = pc.sel(time=slice("2019-01-06", "2019-01-07"))
    assert pc2.n_points == 0


def test_pc_sel_model(pc):
    pc2 = pc.sel(model="m2")
    assert pc2.n_points == 5
    assert pc2.n_models == 1
    assert np.all(pc2.data.m2 == pc.data.m2)
    assert np.all(pc2.raw_mod_data["m2"] == pc.raw_mod_data["m2"])


def test_pc_sel_model_first(pc):
    pc2 = pc.sel(model=0)
    assert pc2.n_points == 5
    assert pc2.n_models == 1
    assert np.all(pc2.data.m1 == pc.data.m1)


def test_pc_sel_model_last(pc):
    pc2 = pc.sel(model=-1)
    assert pc2.n_points == 5
    assert pc2.n_models == 1
    assert np.all(pc2.data.m2 == pc.data.m2)


def test_pc_sel_models_reversed(pc):
    pc2 = pc.sel(model=["m2", "m1"])
    assert pc2.n_points == 5
    assert pc2.n_models == 2
    assert pc2.mod_names == ["m2", "m1"]
    assert np.all(pc2.data.m2 == pc.data.m2)


def test_pc_sel_model_error(pc):
    with pytest.raises(KeyError):
        pc.sel(model="m3")


def test_pc_sel_area(pc):
    bbox = [9.9, 54.9, 10.25, 55.25]
    pc2 = pc.sel(area=bbox)
    assert pc2.n_points == 5
    assert pc2.data.Observation.values.tolist() == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_tc_sel_model(tc):
    tc2 = tc.sel(model="m2")
    assert tc2.n_points == 5
    assert tc2.n_models == 1
    assert np.all(tc2.data.m2 == tc.data.m2)


def test_tc_sel_area(tc):
    bbox = [9.9, 54.9, 10.25, 55.25]
    tc2 = tc.sel(area=bbox)
    assert tc2.n_points == 2
    assert tc2.data.Observation.values.tolist() == [1.0, 2.0]


def test_tc_sel_area_polygon(tc):
    area = [(9.9, 54.9), (10.25, 54.9), (10.25, 55.25), (9.9, 55.25)]
    tc2 = tc.sel(area=area)
    assert tc2.n_points == 2
    assert tc2.data.Observation.values.tolist() == [1.0, 2.0]


def test_tc_sel_time_and_area(tc):
    bbox = [9.9, 54.9, 10.25, 55.25]
    tc2 = tc.sel(time=slice("2019-01-02", "2019-01-03"), area=bbox)
    assert tc2.n_points == 1
    assert tc2.data.Observation.values.tolist() == [2.0]


def test_pc_where(pc):
    pc2 = pc.where(pc.data.Observation > 2.5)
    assert pc2.n_points == 3
    assert pc2.data.Observation.values.tolist() == [3.0, 4.0, 5.0]


def test_pc_where_empty(pc):
    pc2 = pc.where(pc.data.Observation > 10.0)
    assert pc2.n_points == 0


def test_pc_where_derived(pc):
    pc.data["derived"] = pc.data.m1 + pc.data.m2
    pc2 = pc.where(pc.data.derived > 5.0)
    assert pc2.n_points == 3
    assert pc2.data.Observation.values.tolist() == [3.0, 4.0, 5.0]


def test_tc_where_derived(tc):
    x, y = 10.0, 55.0
    dist = np.sqrt((tc.data.x - x) ** 2 + (tc.data.y - y) ** 2)
    # dist = sqrt(2)*[0.1, 0.2, 0.3, 0.4, 0.5]
    tc2 = tc.where(dist > 0.4)
    assert tc2.n_points == 3
    assert tc2.data.Observation.values.tolist() == [3.0, 4.0, 5.0]


def test_tc_where_array(tc):
    cond = np.array([True, False, True, False, True])
    tc2 = tc.where(cond)
    assert tc2.n_points == 3
    assert tc2.data.Observation.values.tolist() == [1.0, 3.0, 5.0]


def test_pc_query(pc):
    pc2 = pc.query("Observation > 2.5")
    assert pc2.n_points == 3
    assert pc2.data.Observation.values.tolist() == [3.0, 4.0, 5.0]


def test_pc_query2(pc):
    pc2 = pc.query("Observation < m2")
    assert pc2.n_points == 4
    assert pc2.data.Observation.values.tolist() == [1.0, 2.0, 3.0, 4.0]


def test_pc_query_empty(pc):
    pc2 = pc.query("Observation > 10.0")
    assert pc2.n_points == 0