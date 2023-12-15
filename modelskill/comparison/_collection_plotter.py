from __future__ import annotations
from typing import Any, List, Union, Optional, Tuple, Sequence, TYPE_CHECKING
from matplotlib.axes import Axes  # type: ignore
import warnings

if TYPE_CHECKING:
    from ._collection import ComparerCollection

import pandas as pd

from .. import metrics as mtr
from ..utils import _get_idx
from ..plotting import taylor_diagram, scatter, TaylorPoint
from ..plotting._misc import _xtick_directional, _ytick_directional, _get_fig_ax


def _default_univarate_title(kind: str, cc: ComparerCollection) -> str:
    return f"{kind} for {cc.n_observations} observations"


class ComparerCollectionPlotter:
    def __init__(self, cc: ComparerCollection) -> None:
        self.cc = cc
        self.is_directional = False

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.scatter(*args, **kwds)

    def scatter(
        self,
        *,
        model=None,
        bins: int | float = 120,
        quantiles: int | Sequence[float] | None = None,
        fit_to_quantiles: bool = False,
        show_points: bool | int | float | None = None,
        show_hist: Optional[bool] = None,
        show_density: Optional[bool] = None,
        backend: str = "matplotlib",
        figsize: Tuple[float, float] = (8, 8),
        xlim: Optional[Tuple[float, float]] = None,
        ylim: Optional[Tuple[float, float]] = None,
        reg_method: str | bool = "ols",
        title: Optional[str] = None,
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        skill_table: Optional[Union[str, List[str], bool]] = None,
        ax: Optional[Axes] = None,
        **kwargs,
    ):
        """Scatter plot showing compared data: observation vs modelled
        Optionally, with density histogram.

        Parameters
        ----------
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
            int: if 'n' (int) given, then 'n' points will be displayed, randomly selected
        show_hist : bool, optional
            show the data density as a a 2d histogram, by default None
        show_density: bool, optional
            show the data density as a colormap of the scatter, by default None. If both `show_density` and `show_hist`
        are None, then `show_density` is used by default.
            for binning the data, the previous kword `bins=Float` is used
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
            False : no regression line,
            by default "ols"
        title : str, optional
            plot title, by default None
        xlabel : str, optional
            x-label text on plot, by default None
        ylabel : str, optional
            y-label text on plot, by default None
        skill_table : str, List[str], bool, optional
            list of modelskill.metrics or boolean, if True then by default modelskill.options.metrics.list.
            This kword adds a box at the right of the scatter plot,
            by default False
        ax : matplotlib axes, optional
            axes to plot on, by default None
        kwargs

        Examples
        ------
        >>> cc.plot.scatter()
        >>> cc.plot.scatter(bins=0.2, backend='plotly')
        >>> cc.plot.scatter(show_points=False, title='no points')
        >>> cc.plot.scatter(xlabel='all observations', ylabel='my model')
        >>> cc.plot.scatter(model='HKZN_v2', figsize=(10, 10))
        >>> cc.plot.scatter(observations=['c2','HKNA'])
        """

        cc = self.cc
        if model is None:
            mod_names = cc.mod_names
        else:
            warnings.warn(
                "The 'model' keyword is deprecated! Instead, filter comparer before plotting cmp.sel(model=...).plot.scatter()",
                FutureWarning,
            )

            if isinstance(model, (str, int)):
                model = [model]
            mod_names = [cc.mod_names[_get_idx(m, cc.mod_names)] for m in model]

        axes = []
        for mod_name in mod_names:
            ax_mod = self._scatter_one_model(
                mod_name=mod_name,
                bins=bins,
                quantiles=quantiles,
                fit_to_quantiles=fit_to_quantiles,
                show_points=show_points,
                show_hist=show_hist,
                show_density=show_density,
                backend=backend,
                figsize=figsize,
                xlim=xlim,
                ylim=ylim,
                reg_method=reg_method,
                title=title,
                xlabel=xlabel,
                ylabel=ylabel,
                skill_table=skill_table,
                ax=ax,
                **kwargs,
            )
            axes.append(ax_mod)
        return axes[0] if len(axes) == 1 else axes

    def _scatter_one_model(
        self,
        *,
        mod_name: str,
        bins: int | float,
        quantiles: int | Sequence[float] | None,
        fit_to_quantiles: bool,
        show_points: bool | int | float | None,
        show_hist: Optional[bool],
        show_density: Optional[bool],
        backend: str,
        figsize: Tuple[float, float],
        xlim: Optional[Tuple[float, float]],
        ylim: Optional[Tuple[float, float]],
        reg_method: str | bool,
        title: Optional[str],
        xlabel: Optional[str],
        ylabel: Optional[str],
        skill_table: Optional[Union[str, List[str], bool]],
        ax: Optional[Axes],
        **kwargs,
    ):
        assert (
            mod_name in self.cc.mod_names
        ), f"Model {mod_name} not found in collection {self.cc.mod_names}"

        cmp = self.cc

        if cmp.n_points == 0:
            raise ValueError("No data found in selection")

        df = cmp.to_dataframe()
        x = df.obs_val.values
        y = df.mod_val.values

        # TODO why the first?
        unit_text = self.cc[0].unit_text

        xlabel = xlabel or f"Observation, {unit_text}"
        ylabel = ylabel or f"Model, {unit_text}"
        title = title or f"{mod_name} vs {cmp.name}"

        skill = None
        units = None
        if skill_table:
            metrics = None if skill_table is True else skill_table

            # TODO why is this here?
            if isinstance(self, ComparerCollectionPlotter) and cmp.n_observations == 1:
                skill = cmp.skill(metrics=metrics)  # type: ignore
            else:
                skill = cmp.mean_skill(metrics=metrics)  # type: ignore
            # TODO improve this
            try:
                units = unit_text.split("[")[1].split("]")[0]
            except IndexError:
                units = ""  # Dimensionless

        if self.is_directional:
            # hide quantiles and regression line
            quantiles = 0
            reg_method = False

        ax = scatter(
            x=x,
            y=y,
            bins=bins,
            quantiles=quantiles,
            fit_to_quantiles=fit_to_quantiles,
            show_points=show_points,
            show_hist=show_hist,
            show_density=show_density,
            backend=backend,
            figsize=figsize,
            xlim=xlim,
            ylim=ylim,
            reg_method=reg_method,
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            skill_df=skill,
            units=units,
            ax=ax,
            **kwargs,
        )

        if backend == "matplotlib" and self.is_directional:
            _xtick_directional(ax, xlim)
            _ytick_directional(ax, ylim)

        return ax

    def kde(self, ax=None, figsize=None, title=None, **kwargs) -> Axes:
        """Plot kernel density estimate of observation and model data.

        Parameters
        ----------
        ax : Axes, optional
            matplotlib axes, by default None
        figsize : tuple, optional
            width and height of the figure, by default None
        title : str, optional
            plot title, by default None
        **kwargs
            passed to pandas.DataFrame.plot.kde()

        Returns
        -------
        Axes
            matplotlib axes

        Examples
        --------
        >>> cc.plot.kde()
        >>> cc.plot.kde(bw_method=0.5)
        >>> cc.plot.kde(bw_method='silverman')

        """
        _, ax = _get_fig_ax(ax, figsize)

        df = self.cc.to_dataframe()
        ax = df.obs_val.plot.kde(
            ax=ax, linestyle="dashed", label="Observation", **kwargs
        )

        for model in self.cc.mod_names:
            df_model = df[df.model == model]
            df_model.mod_val.plot.kde(ax=ax, label=model, **kwargs)

        ax.set_xlabel(f"{self.cc.unit_text}")

        title = (
            _default_univarate_title("Density plot", self.cc)
            if title is None
            else title
        )
        ax.set_title(title)
        ax.legend()

        # remove y-axis, ticks and label
        ax.yaxis.set_visible(False)
        ax.tick_params(axis="y", which="both", length=0)
        ax.set_ylabel("")

        # remove box around plot
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

        if self.is_directional:
            _xtick_directional(ax)

        return ax

    def hist(
        self,
        model=None,
        bins=100,
        title: Optional[str] = None,
        density=True,
        alpha: float = 0.5,
        ax=None,
        figsize: Optional[Tuple[float, float]] = None,
        **kwargs,
    ):
        """Plot histogram of specific model and all observations.

        Wraps pandas.DataFrame hist() method.

        Parameters
        ----------
        model : str, optional
            model name, by default None, i.e. the first model
        bins : int, optional
            number of bins, by default 100
        title : str, optional
            plot title, default: observation name
        density: bool, optional
            If True, draw and return a probability density, by default True
        alpha : float, optional
            alpha transparency fraction, by default 0.5
        ax : matplotlib axes, optional
            axes to plot on, by default None
        figsize : tuple, optional
            width and height of the figure, by default None
        kwargs : other keyword arguments to df.hist()

        Returns
        -------
        matplotlib axes

        Examples
        --------
        >>> cc.plot.hist()
        >>> cc.plot.hist(bins=100)

        See also
        --------
        pandas.Series.hist
        matplotlib.axes.Axes.hist
        """
        from ._comparison import MOD_COLORS

        _, ax = _get_fig_ax(ax, figsize)

        mod_id = _get_idx(model, self.cc.mod_names)
        mod_name = self.cc.mod_names[mod_id]

        title = (
            _default_univarate_title("Histogram", self.cc) if title is None else title
        )

        cmp = self.cc
        df = cmp.to_dataframe()
        kwargs["alpha"] = alpha
        kwargs["density"] = density
        df.mod_val.hist(bins=bins, color=MOD_COLORS[mod_id], ax=ax, **kwargs)
        df.obs_val.hist(
            bins=bins,
            color=self.cc[0].data["Observation"].attrs["color"],
            ax=ax,
            **kwargs,
        )

        ax.legend([mod_name, "observations"])
        ax.set_title(title)
        ax.set_xlabel(f"{self.cc[df.observation.iloc[0]].unit_text}")

        if density:
            ax.set_ylabel("density")
        else:
            ax.set_ylabel("count")

        if self.is_directional:
            _xtick_directional(ax)

        return ax

    def taylor(
        self,
        normalize_std: bool = False,
        aggregate_observations: bool = True,
        figsize: Tuple[float, float] = (7, 7),
        marker: str = "o",
        marker_size: float = 6.0,
        title: str = "Taylor diagram",
    ):
        """Taylor diagram showing model std and correlation to observation
        in a single-quadrant polar plot, with r=std and theta=arccos(cc).

        Parameters
        ----------
        model : (int, str), optional
            name or id of model to be compared, by default all
        observation : (int, str, List[str], List[int])), optional
            name or ids of observations to be compared, by default all
        variable : (str, int), optional
            name or id of variable to be compared, by default first
        start : (str, datetime), optional
            start time of comparison, by default None
        end : (str, datetime), optional
            end time of comparison, by default None
        area : list(float), optional
            bbox coordinates [x0, y0, x1, y1],
            or polygon coordinates[x0, y0, x1, y1, ..., xn, yn],
            by default None
        normalize_std : bool, optional
            plot model std normalized with observation std, default False
        aggregate_observations : bool, optional
            should multiple observations be aggregated before plotting
            (or shown individually), default True
        figsize : tuple, optional
            width and height of the figure (should be square), by default (7, 7)
        marker : str, optional
            marker type e.g. "x", "*", by default "o"
        marker_size : float, optional
            size of the marker, by default 6
        title : str, optional
            title of the plot, by default "Taylor diagram"

        Returns
        -------
        matplotlib.figure.Figure

        Examples
        ------
        >>> cc.plot.taylor()
        >>> cc.plot.taylor(observation="c2")
        >>> cc.plot.taylor(start="2017-10-28", figsize=(5,5))

        References
        ----------
        Copin, Y. (2018). https://gist.github.com/ycopin/3342888, Yannick Copin <yannick.copin@laposte.net>
        """

        if (not aggregate_observations) and (not normalize_std):
            raise ValueError(
                "aggregate_observations=False is only possible if normalize_std=True!"
            )

        metrics = [mtr._std_obs, mtr._std_mod, mtr.cc]
        skill_func = self.cc.mean_skill if aggregate_observations else self.cc.skill
        s = skill_func(
            metrics=metrics,  # type: ignore
        )
        if s is None:
            return

        df = s.to_dataframe()
        ref_std = 1.0 if normalize_std else df.iloc[0]["_std_obs"]

        if isinstance(df.index, pd.MultiIndex):
            df.index = df.index.map("_".join)

        df = df[["_std_obs", "_std_mod", "cc"]].copy()
        df.columns = ["obs_std", "std", "cc"]
        pts = [
            TaylorPoint(
                r.Index, r.obs_std, r.std, r.cc, marker=marker, marker_size=marker_size
            )
            for r in df.itertuples()
        ]

        return taylor_diagram(
            obs_std=ref_std,
            points=pts,
            figsize=figsize,
            normalize_std=normalize_std,
            title=title,
        )
