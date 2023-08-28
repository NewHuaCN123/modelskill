from typing import List, Optional, Tuple, Union

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.legend import Legend
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Polygon, Rectangle


def wind_rose(
    data,
    *,
    labels = ("Measurement", "Model"),
    mag_step: Optional[float] = None,
    n_sectors: int = 16,
    calm_threshold: Optional[float]=None,  # TODO rename to vmin?
    calm_size : Optional[float] = None,
    calm_text: str ="Calm",
    r_step: float = 0.1,
    r_max: Optional[float] = None,
    legend: bool =True,
    cmap1: str = "viridis",
    cmap2: str = "Greys",
    mag_bins: Optional[List[float]] = None,
    max_bin: Optional[float]=None,  # TODO rename to vmax?
    n_dir_labels: Optional[int] = None,
    secondary_dir_step_factor: float = 2.0,
    figsize: Tuple[float,float] = (8,8),
    ax=None,
):

    """Plots a (dual) wind (wave or current) roses with calms.

    The size of the calm is determined by the primary (measurement) data.

    Parameters
    ----------
    data: array-like
        array with 2 or 4 columns (magnitude, direction, magnitude2, direction2)
    labels: tuple of strings. Default= ("Measurement", "Model")
        labels for the legend(s)
    mag_step: float, (optional) Default= None
        discretization for magnitude (delta_r, in radial direction )
    n_sectors: int (optional) Default= 16
    calm_threshold: float (optional) Default= None (auto calculated)
        minimum value for data being counted as valid (i.e. below this is calm)
    resize_calm: bool or float (optional) Default: 0.05
        resize the size of calm in plot. Useful when the calms are very large or small.
    calm_text: str (optional) Default: 'Calm'
        text to display in calm.
    r_step: float (optional) Default= 0.1
        radial axis discretization. By default 0.1 i.e. every 10%.
    r_max: float (optional) Default= None
        maximum radius (%) of plot, e.g. if 50% wanted then r_max=0.5
    max_bin:  float (optional) Default= None
        max value to truncate the data, e.g.,  max_bin=1.0 if hm0=1m is the desired final bin.
    mag_bins : array of floats (optional) Default = None
        force bins to array of values, e.g. when specifying non-equidistant bins.
    legend: boolean. Default= True
        show legend
    cmap1 : string. Default= 'viridis'
        colormap for main axis
    cmap2 : string. Default= 'Greys'
        colormap for secondary axis
    n_dir_labels : int. Default= 4
        number of labels in the polar plot, choose between 4, 8 or 16, default is to use the same as n_sectors
    secondary_dir_step_factor : float. Default= 2.0
        reduce width of secondary axis by this factor
    figsize: tuple(float,float)
        figure size
    ax: Matplotlib axis Default= None
        Matplotlib axis to plot on defined as polar, it can be done using "subplot_kw = dict(projection = 'polar')". Default = None, new axis created.
    

    Returns
    -------
    ax: Matplotlib axis
        Matplotlib axis with the plot
    """
    if hasattr(data, "to_numpy"):
        data = data.to_numpy()
    
    # check that data is array_like
    assert hasattr(data, "__array__"), "data must be array_like"

    data_1 = data[:, 0:2] # primary magnitude and direction
    data_1_max = data_1[:, 0].max()

    ncols = data.shape[1]
    assert ncols in [2, 4], "data must have 2 or 4 columns"
    dual = ncols == 4

    if dual:
        data_2 = data[:, 2:4] # secondary magnitude and direction
        data_2_max = data_2[:, 0].max()
        assert len(labels) == 2, "labels must have 2 elements"
    else:
        data_2 = None
        data_2_max = None

    # magnitude bins
    ui, vmin, vmax = pretty_intervals(
        data_1_max,
        data_2_max,
        mag_bins,
        mag_step,
        calm_threshold,
        max_bin,
    )

    dir_step = 360 // n_sectors
    half_dir_step = dir_step / 2

    n_dir_labels = n_sectors if n_dir_labels is None else n_dir_labels

    thetai = np.linspace(
        start=half_dir_step,
        stop=360 + half_dir_step,
        num=int(((360 + half_dir_step) - half_dir_step) / dir_step + 1),
    )
    thetac = thetai[:-1] + half_dir_step

    mask_1 = data_1[:, 0] >= vmin    

    # compute total calms
    n = len(data_1)
    calm = len(data_1[~mask_1]) / n   

    counts = _calc_masked_histogram2d(data=data_1, mask=mask_1, ui=ui, thetai=thetai)

    if dual:
        mask_2 = data_2[:, 0] >= vmin
        calm2 = len(data_2[~mask_2]) / n
        counts_2 = _calc_masked_histogram2d(
            data=data_2, mask=mask_2, ui=ui, thetai=thetai, n=len(data_1)
        )
        assert counts.shape == counts_2.shape

    ri, rmax = _calc_radial_ticks(counts=counts, step=r_step, stop=r_max)

    # Resize calm
    # TODO this overwrites the calm value calculated above
    if calm_size is not None:
        calm = calm_size

    cmap = _get_cmap(cmap1)

    if ax is None:
        _, ax = plt.subplots(figsize=figsize, subplot_kw=dict(projection="polar"))

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    dir_labels = directional_labels(n_dir_labels)
    grid = np.linspace(0, 360, n_dir_labels + 1)[:-1]
    ax.set_thetagrids(grid, dir_labels)

    # ax.tick_params(pad=-24)

    ax.set_ylim(0, calm + rmax)
    ax.set_yticks(ri + calm)
    tick_labels = [f"{tick * 100 :.0f}%" for tick in ri]
    ax.set_yticklabels(tick_labels)
    ax.set_rlabel_position(5)
    
    if vmin > 0:
        _add_calms_to_ax(ax, threshold=calm, text=calm_text)

    # primary histogram (model)
    p = _create_patch(thetac=thetac, dir_step=dir_step, calm=calm, ui=ui, counts=counts, cmap=cmap, vmax=vmax)
    ax.add_collection(p)

    if legend:
        _add_legend_to_ax(
            ax,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            ui=ui,
            calm=calm,
            counts=counts,
            label=labels[0],
            primary=True,
            dual=dual,
        )

    if dual:
        # add second histogram (observation)
        cmap = _get_cmap(cmap2)

        # TODO should this be calm2?
        p = _create_patch(thetac=thetac, dir_step=dir_step, calm=calm, ui=ui, counts=counts_2, cmap=cmap, vmax=vmax, dir_step_factor=secondary_dir_step_factor)
        ax.add_collection(p)

        if legend:
            _add_legend_to_ax(
                ax,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                ui=ui,
                calm=calm2,
                counts=counts_2,
                label=labels[1],
                primary=False,
                dual=dual,
                )

    return ax


def directional_labels(n: int) -> Tuple[str, ...]:
    """Return labels for n directions.

    Parameters
    ----------
    n : int
        Number of directions. Must be 4, 8 or 16.

    Returns
    -------
    Tuple[str, ...]
        labels

    Examples
    --------
    >>> directional_labels(4)
    ('N', 'E', 'S', 'W')
    """
    if n == 4:
        return ("N", "E", "S", "W")
    elif n == 8:
        return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    elif n == 16:
        return (
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        )
    else:
        raise ValueError("n must be 4, 8 or 16")


def pretty_intervals(
    xmax: float,
    ymax: Optional[float] = None,
    mag_bins: Optional[List[float]] = None,
    mag_step: Optional[float] = None,
    vmin: Optional[float] = None,
    max_bin: Optional[float] = None,
    n_decimals: int = 3,
) -> Tuple[np.ndarray, float, float]:
    """Pretty intervals for the magnitude bins"""

    if mag_bins is not None:
        assert len(mag_bins) >= 3, "Must have at least 3 bins"
        mag_bins_ = np.array(mag_bins)
        ui = np.concatenate((mag_bins_, mag_bins_[[-1]] * 999)) # TODO 999?
        vmin = ui[0]
        max_bin = ui[-2]
        dbin = np.diff(ui)[-2]
        vmax = max_bin + dbin * 2  # TODO what is happening here?

    else:
        if mag_step is None:
            mag_step = _calc_mag_step(xmax, ymax)

        if vmin is None:
            vmin = mag_step

        if ymax is None:
            magmax = xmax
        else:
            magmax = max(xmax, ymax)
        # Bins
        ui = np.arange(vmin, magmax, mag_step)
        ui = np.append(ui, xmax)

        if max_bin is None:
            max_bin = magmax / 2
        dbin = ui[1] - ui[0]
        vmax = max_bin + dbin * 2
        ui = np.arange(ui[0], vmax, dbin)
        ui[-1] = (
            ui[-1] * 2
        )  # safety factor * 2 as sometimes max is not in the iterations
        # Round bins to make them pretty
        ui = ui.round(n_decimals)

    # TODO return a better object?
    return ui, vmin, vmax


def _create_patch(thetac, dir_step, calm, ui, counts, cmap, vmax, dir_step_factor=1.0) -> PatchCollection:

    arc_res = dir_step
    # reduced width of arcs for plot on top of each other
    dir_step = dir_step / dir_step_factor

    norm = mpl.colors.Normalize(vmin=0, vmax=vmax)

    patches = []
    colors = []
    cumcount = counts.cumsum(axis=0)

    arc_x = np.deg2rad(
        np.linspace(thetac - dir_step / 2, thetac + dir_step / 2, arc_res)
    )
    
    # TODO consider if this section can be written in a clearer way
    # Loop through magnitudes
    for i, mag in enumerate(ui[1:]):
        # Loop through directions
        for j, _ in enumerate(counts[i]):
            arc_xj = np.concatenate([arc_x[:, j], np.flip(arc_x[:, j])])
            arc_yj = np.concatenate(
                [np.full(arc_res, calm), np.full(arc_res, calm + cumcount[i, j])]
            )

            xy = np.array((arc_xj, arc_yj)).T
            polygon = Polygon(xy=xy, closed=True)
            patches.append(polygon)
            colors.append(cmap(norm(mag)))

    p = PatchCollection(
        np.flip(patches),
        facecolors=np.flip(colors, axis=0),
        edgecolor="k",
        linewidth=0.5,
    )

    return p

def _calc_mag_step(xmax: float, ymax: Optional[float] = None, factor: float = 16.0):
    """
    Calculate the magnitude step size for a rose plot.

    Parameters
    ----------
    x : float
        The maximum value of the histogram.
    y : float, optional
        The maximum value of the histogram.
    factor : float, optional
        The factor to use to calculate the magnitude step size, by default 16.0

    Returns
    -------
    float
    """
    mag_step = np.round(xmax / factor, 1)
    if mag_step == 0:
        mag_step = np.round(xmax / factor, 2)

    if ymax is None:
        return mag_step
    
    mag_step2 = np.round(ymax / factor, 1)
    if mag_step2 == 0:
        mag_step2 = np.round(ymax / factor, 2)
    mag_step = max(mag_step, mag_step2)
    return mag_step


def _calc_masked_histogram2d(*, data, mask, ui, thetai, n: Optional[int]=None) -> np.ndarray:
    
    if n is None:
        n = len(data)
    counts, _, _ = np.histogram2d(
        data[mask][:, 0],
        data[mask][:, 1],
        bins=[ui, thetai],
    )
    counts = counts / n
    return counts



def _calc_radial_ticks(
    *, counts: np.ndarray, step: float, stop: Optional[float]
) -> np.ndarray:
    cmax = counts.sum(axis=0).max()
    if stop is None:
        rmax = np.ceil((cmax + step) / step) * step
    else:
        rmax = stop

    ri = np.linspace(0, rmax, int(rmax / step) + 1)
    ri = ri[1:-1]

    return ri, rmax


def _add_calms_to_ax(ax, *, threshold: np.ndarray, text: str) -> None:
    ax.bar(np.pi, threshold, color="white", ec="k", zorder=0)
    ax.bar(
        np.pi, threshold, width=2 * np.pi, label="_nolegend_", color="white", zorder=3
    )
    ax.text(
        0.5,
        0.5,
        text,
        horizontalalignment="center",
        verticalalignment="center",
        transform=ax.transAxes,
    )


def _add_legend_to_ax(
    ax, *, cmap,vmin,vmax, ui, calm, counts, label, primary: bool, dual=False
) -> None:

    norm = mpl.colors.Normalize(vmin=0, vmax=vmax)
    colors = [cmap(norm(x)) for x in ui]

    percentages = np.sum(counts, axis=1) * 100

    legend_items = []

    for j in range(len(ui[1:-1])):
        legend_items.append(f"{np.round(ui[j],2)} - {np.round(ui[j+1],2)}")
    items = [f"<{vmin} ({np.round(calm*100,2)}%)"]
    items.extend(legend_items)
    items.append(f">= {ui[-2]} ({np.round(percentages[-1], 2)}%)")

    handles = [Rectangle((0, 0), 1, 1, color=c, ec="k") for c in colors]
    handles[0].set_color("white")
    handles[0].set_ec("k")

    if primary:
        bbox_to_anchor = (1.05, -0.06, 0.1, 0.8)
        loc = "lower left"
    else:
        bbox_to_anchor = (-0.13, -0.06, 0.1, 0.8)
        loc = "lower right"

    # TODO figure out how to make this work properly
    if not dual:
        bbox_to_anchor = (-0.05, 0.0)
        loc = 'lower right'

    leg = Legend(
        ax,
        handles[::-1],
        items[::-1],
        frameon=True,
        title=label,
        bbox_to_anchor=bbox_to_anchor,
        loc=loc,
    )
    box_width = 0.32
    
    if primary:
        ax_left = ax.inset_axes([-box_width * 1.15, -0.05, box_width * 1.15, 0.5])
        ax_left.axis("off")
    else:
        ax_right = ax.inset_axes([1.15, -0.05, box_width * 1.15, 0.5])
        ax_right.axis("off")
    ax.add_artist(leg)


def _add_watermark_to_ax(ax, watermark: str) -> None:
    text = AnchoredText(
        watermark,
        "center right",
        frameon=False,
        borderpad=-27.5,
        prop=dict(fontsize="xx-small", alpha=0.15, rotation=90),
    )
    ax.add_artist(text)


def _get_cmap(cmap: Union[str, mpl.colors.ListedColormap]) -> mpl.colors.ListedColormap:
    if isinstance(cmap, str):
        return mpl.colormaps[cmap]
    elif isinstance(cmap, mpl.colors.ListedColormap):
        return cmap
    else:
        raise ValueError(f"Invalid cmap {cmap}")