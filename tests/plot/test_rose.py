import numpy as np
import pytest

import mikeio
from modelskill.rose import wind_rose, pretty_intervals


@pytest.fixture
def wave_data_model_obs():
    """
    <mikeio.Dataset>
    items:
    0:  China_Model: Sign. Wave Height <Significant wave height> (meter)
    1:  China_Measured: Sign. Wave Height <Significant wave height> (meter)
    2:  China_Model: Mean Wave Direction <Mean Wave Direction> (degree)
    3:  China_Measured: Mean Wave Direction <Mean Wave Direction> (degree)
    """
    ds = mikeio.read("tests/testdata/wave_dir.dfs0")
    df = ds[[0, 2, 1, 3]].to_dataframe()
    return df


def test_rose(wave_data_model_obs):
    data = wave_data_model_obs.to_numpy()
    ax = wind_rose(data, mag_step=0.25, cmap1="jet")
    assert ax is not None


def test_pretty_intervals_respects_defined_intervals():
    data1 = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    data2 = np.array([0.01, 0.2, 0.3, 0.4, 0.5, 0.6])
    ui, vmin, vmax = pretty_intervals(
        data_1=data1, data_2=data2, mag_bins=[0.1, 0.2, 0.45]
    )
    assert vmin == 0.1
    assert vmax == 0.95  # TODO why?

    # The computed intervals has one more than the mag_bins
    assert list(ui[:-1]) == [0.1, 0.2, 0.45]

    # The last interval is larger than the second last
    assert ui[-1] > ui[-2]


def test_pretty_intervals():
    data1 = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    data2 = np.array([0.01, 0.2, 0.3, 0.4, 0.5, 0.6])
    ui, vmin, vmax = pretty_intervals(
        data_1=data1, data_2=data2, vmin=0.2, mag_step=0.1
    )
    # TODO WIP
    assert vmin == 0.2
    assert vmax == 0.5  # TODO is this correct?
    assert len(ui) == 3
