from __future__ import annotations
from typing import Optional, Sequence, Tuple

import matplotlib.colors as colors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patches
from matplotlib.axes import Axes
from matplotlib.ticker import MaxNLocator
from scipy import interpolate

import modelskill.settings as settings
from modelskill.settings import options

from ..metrics import _linear_regression
from ._misc import quantiles_xy, sample_points, format_skill_df


def scatter(
    x: np.ndarray,
    y: np.ndarray,
    *,
    bins: int | float = 20,
    quantiles: int | Sequence[float] | None = None,
    fit_to_quantiles: bool = False,
    show_points: bool | int | float | None = None,
    show_hist: Optional[bool] = None,
    show_density: Optional[bool] = None,
    norm: Optional[colors.Normalize] = None,
    backend: str = "matplotlib",
    figsize: Tuple[float, float] = (8, 8),
    xlim: Optional[Tuple[float, float]] = None,
    ylim: Optional[Tuple[float, float]] = None,
    reg_method: str | bool = "ols",
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    skill_df: Optional[pd.DataFrame] = None,
    units: Optional[str] = "",
    **kwargs,
):
    """Scatter plot showing compared data: observation vs modelled
    Optionally, with density histogram.

    Parameters
    ----------
    x: np.array
        X values e.g model values, must be same length as y
    y: np.array
        Y values e.g observation values, must be same length as x
    bins: (int, float, sequence), optional
        bins for the 2D histogram on the background. By default 20 bins.
        if int, represents the number of bins of 2D
        if float, represents the bin size
        if sequence (list of int or float), represents the bin edges
    quantiles: (int, sequence), optional
        number of quantiles for QQ-plot, by default None and will depend on the scatter data length (10, 100 or 1000)
        if int, this is the number of points
        if sequence (list of floats), represents the desired quantiles (from 0 to 1)
    fit_to_quantiles: bool, optional, by default False
        by default the regression line is fitted to all data, if True, it is fitted to the quantiles
        which can be useful to represent the extremes of the distribution
    show_points : (bool, int, float), optional
        Should the scatter points be displayed?
        None means: show all points if fewer than 1e4, otherwise show 1e4 sample points, by default None.
        float: fraction of points to show on plot from 0 to 1. eg 0.5 shows 50% of the points.
        int: if 'n' (int) given, then 'n' points will be displayed, randomly selected.
    show_hist : bool, optional
        show the data density as a 2d histogram, by default None
    show_density: bool, optional
        show the data density as a colormap of the scatter, by default None. If both `show_density` and `show_hist`
        are None, then `show_density` is used by default.
        for binning the data, the previous kword `bins=Float` is used
    norm : matplotlib.colors.Normalize
        colormap normalization
        If None, defaults to matplotlib.colors.PowerNorm(vmin=1,gamma=0.5)
    backend : str, optional
        use "plotly" (interactive) or "matplotlib" backend, by default "matplotlib"
    figsize : tuple, optional
        width and height of the figure, by default (8, 8)
    xlim : tuple, optional
        plot range for the observation (xmin, xmax), by default None
    ylim : tuple, optional
        plot range for the model (ymin, ymax), by default None
    reg_method : str or bool, optional
        method for determining the regression line
        "ols" : ordinary least squares regression
        "odr" : orthogonal distance regression,
        False : no regression line
        by default "ols"
    title : str, optional
        plot title, by default None
    xlabel : str, optional
        x-label text on plot, by default None
    ylabel : str, optional
        y-label text on plot, by default None
    skill_df : dataframe, optional
        dataframe with skill (stats) results to be added to plot, by default None
    units : str, optional
        user default units to override default units, eg 'metre', by default None
    kwargs
    """
    if show_hist is None and show_density is None:
        # Default: points density
        show_density = True

    if len(x) != len(y):
        raise ValueError("x & y are not of equal length")

    if norm is None:
        # Default: PowerNorm with gamma of 0.5
        norm = colors.PowerNorm(vmin=1, gamma=0.5)

    x_sample, y_sample = sample_points(x, y, show_points)
    xq, yq = quantiles_xy(x, y, quantiles)

    xmin, xmax = x.min(), x.max()
    ymin, ymax = y.min(), y.max()
    xymin = min([xmin, ymin])
    xymax = max([xmax, ymax])

    nbins_hist, binsize = _get_bins(bins, xymin=xymin, xymax=xymax)

    if xlim is None:
        xlim = (xymin - binsize, xymax + binsize)

    if ylim is None:
        ylim = (xymin - binsize, xymax + binsize)

    x_trend = np.array([xlim[0], xlim[1]])

    if show_hist and show_density:
        raise TypeError(
            "if `show_hist=True` then `show_density` must be either `False` or `None`"
        )

    z = None
    if show_density and len(x_sample) > 0:
        if not isinstance(bins, (float, int)):
            raise TypeError(
                "if `show_density=True` then bins must be either float or int"
            )

        # calculate density data
        z = __scatter_density(x_sample, y_sample, binsize=binsize)
        idx = z.argsort()
        # Sort data by colormaps
        x_sample, y_sample, z = x_sample[idx], y_sample[idx], z[idx]
        # scale Z by sample size
        z = z * len(x) / len(x_sample)

    PLOTTING_BACKENDS = {
        "matplotlib": _scatter_matplotlib,
        "plotly": _scatter_plotly,
    }

    if backend not in PLOTTING_BACKENDS:
        raise ValueError(f"backend must be one of {list(PLOTTING_BACKENDS.keys())}")

    return PLOTTING_BACKENDS[backend](
        x=x,
        y=y,
        x_sample=x_sample,
        y_sample=y_sample,
        z=z,
        xq=xq,
        yq=yq,
        x_trend=x_trend,
        show_density=show_density,
        norm=norm,
        show_points=show_points,
        show_hist=show_hist,
        nbins_hist=nbins_hist,
        reg_method=reg_method,
        xlabel=xlabel,
        ylabel=ylabel,
        figsize=figsize,
        xlim=xlim,
        ylim=ylim,
        title=title,
        skill_df=skill_df,
        units=units,
        fit_to_quantiles=fit_to_quantiles,
        **kwargs,
    )


def _scatter_matplotlib(
    *,
    x,
    y,
    x_sample,
    y_sample,
    z,
    xq,
    yq,
    x_trend,
    show_density,
    show_points,
    show_hist,
    norm,
    nbins_hist,
    reg_method,
    xlabel,
    ylabel,
    figsize,
    xlim,
    ylim,
    title,
    skill_df,
    units,
    fit_to_quantiles,
    **kwargs,
) -> Axes:
    _, ax = plt.subplots(figsize=figsize)

    plt.plot(
        [xlim[0], xlim[1]],
        [xlim[0], xlim[1]],
        label=options.plot.scatter.oneone_line.label,
        c=options.plot.scatter.oneone_line.color,
        zorder=3,
    )

    if show_points is None or show_points:
        if show_density:
            c = z
            norm_ = norm
        else:
            c = "0.25"
            norm_ = None
        plt.scatter(
            x_sample,
            y_sample,
            c=c,
            s=options.plot.scatter.points.size,
            alpha=options.plot.scatter.points.alpha,
            marker=".",
            label=options.plot.scatter.points.label,
            zorder=1,
            norm=norm_,
            **kwargs,
        )
    if len(xq) > 0:
        plt.plot(
            xq,
            yq,
            options.plot.scatter.quantiles.marker,
            label=options.plot.scatter.quantiles.label,
            c=options.plot.scatter.quantiles.color,
            zorder=4,
            markeredgecolor=options.plot.scatter.quantiles.markeredgecolor,
            markeredgewidth=options.plot.scatter.quantiles.markeredgewidth,
            markersize=options.plot.scatter.quantiles.markersize,
            **settings.get_option("plot.scatter.quantiles.kwargs"),
        )

    if reg_method:
        if fit_to_quantiles:
            slope, intercept = _linear_regression(
                obs=xq, model=yq, reg_method=reg_method
            )
        else:
            slope, intercept = _linear_regression(obs=x, model=y, reg_method=reg_method)

        plt.plot(
            x_trend,
            intercept + slope * x_trend,
            **settings.get_option("plot.scatter.reg_line.kwargs"),
            label=_reglabel(
                slope=slope, intercept=intercept, fit_to_quantiles=fit_to_quantiles
            ),
            zorder=2,
        )

    if show_hist:
        plt.hist2d(x, y, bins=nbins_hist, cmin=0.01, zorder=0.5, norm=norm, **kwargs)

    plt.legend(**settings.get_option("plot.scatter.legend.kwargs"))
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.axis("square")
    plt.xlim([xlim[0], xlim[1]])
    plt.ylim([ylim[0], ylim[1]])
    plt.minorticks_on()
    plt.grid(which="both", axis="both", linewidth="0.2", color="k", alpha=0.6)
    max_cbar = None
    if show_hist or (show_density and show_points):
        cbar = plt.colorbar(fraction=0.046, pad=0.04)
        ticks = cbar.ax.get_yticks()
        max_cbar = ticks[-1]
        cbar.set_label("# points")
        cbar.ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    plt.title(title)
    # Add skill table
    if skill_df is not None:
        df = skill_df.df
        assert isinstance(df, pd.DataFrame)
        _plot_summary_table(df, units, max_cbar=max_cbar)
    return ax


def _scatter_plotly(
    *,
    x,
    y,
    x_sample,
    y_sample,
    z,
    xq,
    yq,
    x_trend,
    show_density,
    show_points,
    norm,  # TODO not used by plotly, remove or keep for consistency?
    show_hist,
    nbins_hist,
    reg_method,
    xlabel,
    ylabel,
    figsize,  # TODO not used by plotly, remove or keep for consistency?
    xlim,
    ylim,
    title,
    skill_df,  # TODO implement
    units,  # TODO implement
    fit_to_quantiles,  # TODO implement
    **kwargs,
):
    import plotly.graph_objects as go

    data = [
        go.Scatter(x=xlim, y=xlim, name="1:1", mode="lines", line=dict(color="blue")),
    ]

    if reg_method:
        if fit_to_quantiles:
            slope, intercept = _linear_regression(
                obs=xq, model=yq, reg_method=reg_method
            )
        else:
            slope, intercept = _linear_regression(obs=x, model=y, reg_method=reg_method)

        regression_line = go.Scatter(
            x=x_trend,
            y=intercept + slope * x_trend,
            name=_reglabel(
                slope=slope, intercept=intercept, fit_to_quantiles=fit_to_quantiles
            ),
            mode="lines",
            line=dict(color="red"),
        )
        data.append(regression_line)

    if show_hist:
        data.append(
            go.Histogram2d(
                x=x,
                y=y,
                nbinsx=nbins_hist,
                nbinsy=nbins_hist,
                colorscale=[
                    [0.0, "rgba(0,0,0,0)"],
                    [0.1, "purple"],
                    [0.5, "green"],
                    [1.0, "yellow"],
                ],
                colorbar=dict(title="# of points"),
            )
        )

    if show_points is None or show_points:
        if show_density:
            c = z
            cbar = dict(thickness=20, title="# of points")
        else:
            c = "black"
            cbar = None
        data.append(
            go.Scatter(
                x=x_sample,
                y=y_sample,
                mode="markers",
                name="Data",
                marker=dict(color=c, opacity=0.5, size=3.0, colorbar=cbar),
            )
        )
    if len(xq) > 0:
        data.append(
            go.Scatter(
                x=xq,
                y=yq,
                name=options.plot.scatter.quantiles.label,
                mode="markers",
                marker_symbol="x",
                marker_color=options.plot.scatter.quantiles.color,
                marker_line_color="midnightblue",
                marker_line_width=0.6,
            )
        )

    defaults = {"width": 600, "height": 600}
    defaults = {**defaults, **kwargs}

    layout = layout = go.Layout(
        legend=dict(x=0.01, y=0.99),
        yaxis=dict(scaleanchor="x", scaleratio=1),
        title=dict(text=title, xanchor="center", yanchor="top", x=0.5, y=0.9),
        yaxis_title=ylabel,
        xaxis_title=xlabel,
        **defaults,
    )

    fig = go.Figure(data=data, layout=layout)
    fig.update_xaxes(range=xlim)
    fig.update_yaxes(range=ylim)
    fig.show()  # Should this be here


def _reglabel(slope: float, intercept: float, fit_to_quantiles: bool) -> str:
    sign = "" if intercept < 0 else "+"
    if fit_to_quantiles:
        fit = "QQ fit"
    else:
        fit = "Fit"
    return f"{fit}: y={slope:.2f}x{sign}{intercept:.2f}"


def _get_bins(bins: int | float, xymin, xymax) -> Tuple[int, float]:
    assert xymax >= xymin
    xyspan = xymax - xymin

    if isinstance(bins, int):
        nbins_hist: int = bins
        binsize: float = xyspan / nbins_hist
    elif isinstance(bins, float):
        binsize = bins
        nbins_hist = xyspan // binsize
    else:
        raise TypeError("bins must be a number")

    assert nbins_hist > 0

    return nbins_hist, binsize


def _plot_summary_border(
    figure_transform,
    x0,
    y0,
    dx,
    dy,
    borderpad=0.01,
) -> None:
    ## Load settings
    bbox_kwargs = {}
    bbox_kwargs.update(settings.get_option("plot.scatter.legend.bbox"))
    if (
        "boxstyle" in bbox_kwargs and "pad" not in bbox_kwargs["boxstyle"]
    ):  # default padding results in massive bbox
        bbox_kwargs["boxstyle"] = bbox_kwargs["boxstyle"] + f",pad={borderpad}"
    else:
        bbox_kwargs["boxstyle"] = f"square,pad={borderpad}"
    lgkw = settings.get_option("plot.scatter.legend.kwargs")
    if "edgecolor" in lgkw:
        bbox_kwargs["edgecolor"] = lgkw["edgecolor"]

    ## Define rectangle
    bbox = patches.FancyBboxPatch(
        (x0 - borderpad, y0 - borderpad),
        dx + borderpad * 2,
        dy + borderpad * 2,
        transform=figure_transform,
        clip_on=False,
        **bbox_kwargs,
    )

    plt.gca().add_patch(bbox)


def _plot_summary_table(
    df: pd.DataFrame, units: str, max_cbar: Optional[float] = None
) -> None:
    lines = format_skill_df(df, units)
    text_ = ["\n".join(lines[:, i]) for i in range(lines.shape[1])]

    if max_cbar is None:
        x = 0.93
    elif max_cbar < 1e3:
        x = 0.99
    elif max_cbar < 1e4:
        x = 1.01
    elif max_cbar < 1e5:
        x = 1.03
    elif max_cbar < 1e6:
        x = 1.05
    else:
        # When more than 1e6 samples, matplotlib changes to scientific notation
        x = 0.97

    fig = plt.gcf()
    figure_transform = fig.transFigure.get_affine()

    # General text settings
    txt_settings = dict(
        fontsize=options.plot.scatter.legend.fontsize,
    )

    # Column 1
    text_columns = []
    dx = 0
    for ti in text_:
        text_col_i = fig.text(x + dx, 0.6, ti, **txt_settings)
        ## Render, and get width
        plt.draw()
        dx = (
            dx
            + figure_transform.inverted().transform(
                [text_col_i.get_window_extent().bounds[2], 0]
            )[0]
        )
        text_columns.append(text_col_i)

    # Plot border
    ## Define coordintes
    x0, y0 = figure_transform.inverted().transform(
        text_columns[0].get_window_extent().bounds[0:2]
    )
    _, dy = figure_transform.inverted().transform(
        (0, text_columns[0].get_window_extent().bounds[3])
    )

    _plot_summary_border(figure_transform, x0, y0, dx, dy)


def __scatter_density(x, y, binsize: float = 0.1, method: str = "linear"):
    """Interpolates scatter data on a 2D histogram (gridded) based on data density.

    Parameters
    ----------
    x: np.array
        X values e.g model values, must be same length as y
    y: np.array
        Y values e.g observation values, must be same length as x
    binsize: float, optional
        2D histogram (bin) resolution, by default = 0.1
    method: str, optional
        Scipy griddata interpolation method, by default 'linear'

    Returns
    ----------
    Z_grid: np.array
        Array with the colors based on histogram density
    """

    hist, cxy = __hist2d(x, y, binsize)

    # Grid-data
    xg, yg = np.meshgrid(cxy, cxy)
    xg = xg.ravel()
    yg = yg.ravel()

    ## Interpolate histogram density data to scatter data
    Z_grid = interpolate.griddata((xg, yg), hist, (x, y), method=method)

    # Replace negative values (should there be some) in case of 'cubic' interpolation
    Z_grid[(Z_grid < 0)] = 0

    return Z_grid


def __hist2d(x, y, binsize):
    """Calculates 2D histogram (gridded) of data.

    Parameters
    ----------
    x: np.array
        X values e.g model values, must be same length as y
    y: np.array
        Y values e.g observation values, must be same length as x
    binsize: float, optional
        2D histogram (bin) resolution, by default = 0.1

    Returns
    ----------
    histodata: np.array
        2D-histogram data
    cxy: np.array
        Center points of the histogram bins
    exy: np.array
        Edges of the histogram bins
    """
    # Make linear-grid for interpolation
    minxy = min(min(x), min(y)) - binsize
    maxxy = max(max(x), max(y)) + binsize
    # Center points of the bins
    cxy = np.arange(minxy, maxxy, binsize)
    # Edges of the bins
    exy = np.arange(minxy - binsize * 0.5, maxxy + binsize * 0.5, binsize)
    if exy[-1] <= cxy[-1]:
        # sometimes, given the bin size, the edges array ended before (left side) of the bins-center array
        # in such case, and extra half-bin is added at the end
        exy = np.arange(minxy - binsize * 0.5, maxxy + binsize, binsize)

    # Calculate 2D histogram
    histodata, _, _ = np.histogram2d(x, y, [exy, exy])

    # Histogram values
    hist = []
    for j in range(len(cxy)):
        for i in range(len(cxy)):
            hist.append(histodata[i, j])

    return hist, cxy
