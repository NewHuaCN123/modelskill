<img src="https://raw.githubusercontent.com/DHI/modelskill/main/images/logo/modelskill.svg" width="300">

# ModelSkill: Flexible Model skill evaluation.
 ![Python version](https://img.shields.io/pypi/pyversions/modelskill.svg) 
![Python package](https://github.com/DHI/modelskill/actions/workflows/full_test.yml/badge.svg) [![PyPI version](https://badge.fury.io/py/modelskill.svg)](https://badge.fury.io/py/modelskill)

[ModelSkill](https://github.com/DHI/modelskill) is a python package for scoring [MIKE](https://www.mikepoweredbydhi.com) models (other models can be evaluated as well). 

Read more about the [vision and scope](https://dhi.github.io/modelskill/vision.html). Contribute with new ideas in the [discussion](https://github.com/DHI/modelskill/discussions), report an [issue](https://github.com/DHI/modelskill/issues) or browse the [API documentation](https://dhi.github.io/modelskill/api.html). Access observational data (e.g. altimetry data) from the sister library [WatObs](https://github.com/DHI/watobs). 


## Use cases

[ModelSkill](https://github.com/DHI/modelskill) would like to be your companion during the different phases of a MIKE modelling workflow.

* Model setup - exploratory phase   
* Model calibration
* Model validation and reporting - communicate your final results

## Installation

From [pypi](https://pypi.org/project/modelskill/):

`> pip install modelskill`

Or the development version:

`> pip install https://github.com/DHI/modelskill/archive/main.zip`


## Example notebooks

* [Quick_and_dirty_compare.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/Quick_and_dirty_compare.ipynb)
* [SW_DutchCoast.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/SW_DutchCoast.ipynb)
* [Multi_model_comparison.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/Multi_model_comparison.ipynb)
* [Multi_variable_comparison.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/Multi_variable_comparison.ipynb)
* [Track_comparison.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/Track_comparison.ipynb) (including global wave model example)
* [Spatial_skill.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/Spatial_skill.ipynb) (satellite tracks, skill aggregated on spatial bins)
* [NetCDF_ModelResult.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/NetCDF_ModelResult.ipynb)
* [Combine_comparers.ipynb](https://nbviewer.jupyter.org/github/DHI/modelskill/blob/main/notebooks/Combine_comparers.ipynb)


## Workflow

1. Define **ModelResults**
2. Define **Observations**
3. **Compare** Observations and ModelResults
4. Do plotting, statistics, reporting using the **Comparer**

Read more about the workflow in the [getting started guide](https://dhi.github.io/modelskill/getting-started.html).


## Example of use

Start by defining model results and observations:

```python
>>> import modelskill as ms
>>> mr = ms.ModelResult("HKZN_local_2017_DutchCoast.dfsu", name="HKZN_local", item=0)
>>> HKNA = ms.PointObservation("HKNA_Hm0.dfs0", item=0, x=4.2420, y=52.6887, name="HKNA")
>>> EPL = ms.PointObservation("eur_Hm0.dfs0", item=0, x=3.2760, y=51.9990, name="EPL")
>>> c2 = ms.TrackObservation("Alti_c2_Dutch.dfs0", item=3, name="c2")
```

Then, connect observations and model results, and extract data at observation points:

```python
>>> cc = ms.compare([HKNA, EPL, c2], mr)
```

With the comparer object, cc, all sorts of skill assessments and plots can be made:

```python
>>> cc.skill().round(2)
               n  bias  rmse  urmse   mae    cc    si    r2
observation                                                
HKNA         385 -0.20  0.35   0.29  0.25  0.97  0.09  0.99
EPL           66 -0.08  0.22   0.20  0.18  0.97  0.07  0.99
c2           113 -0.00  0.35   0.35  0.29  0.97  0.12  0.99
```

### Overview of observation locations

```python
ms.plot_spatial_overview([HKNA, EPL, c2], mr, figsize=(7,7))
```

![map](https://raw.githubusercontent.com/DHI/modelskill/main/images/map.png)



### Scatter plot

```python
cc.plot.scatter()
```

![scatter](https://raw.githubusercontent.com/DHI/modelskill/main/images/scatter.png)

### Timeseries plot

Timeseries plots can either be static and report-friendly ([matplotlib](https://matplotlib.org/)) or interactive with zoom functionality ([plotly](https://plotly.com/python/)).

```python
cc["HKNA"].plot.timeseries(width=1000, backend="plotly")
```

![timeseries](https://raw.githubusercontent.com/DHI/modelskill/main/images/plotly_timeseries.png)
