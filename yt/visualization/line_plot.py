"""
A mechanism for plotting field values along a line through a dataset



"""

#-----------------------------------------------------------------------------
# Copyright (c) 2017, yt Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

import numpy as np

from collections import defaultdict
from yt.funcs import \
    iterable, \
    mylog
from yt.units.unit_object import \
    Unit
from yt.units.yt_array import \
    YTArray
from yt.visualization.base_plot_types import \
    PlotMPL
from yt.visualization.plot_container import \
    PlotContainer, \
    PlotDictionary, \
    log_transform, \
    linear_transform, \
    invalidate_plot

class LineBuffer(object):
    def __init__(self, ds, start_point, end_point, npoints, label=None):
        self.ds = ds
        self.start_point = _validate_point(start_point, ds, start=True)
        self.end_point = _validate_point(end_point, ds)
        self.npoints = npoints
        self.label = label
        self.data = {}

    def keys(self):
        return self.data.keys()

    def __setitem__(self, item, val):
        self.data[item] = val

    def __getitem__(self, item):
        if item in self.data: return self.data[item]
        mylog.info("Making a line buffer with %d points of %s" % \
            (self.npoints, item))
        self.points, self.data[item] = self.ds.coordinates.pixelize_line(item,
                                                               self.start_point,
                                                               self.end_point,
                                                               self.npoints)

        return self.data[item]

    def __delitem__(self, item):
        del self.data[item]


class LinePlotDictionary(PlotDictionary):
    def __init__(self, data_source):
        super(LinePlotDictionary, self).__init__(data_source)
        self.known_dimensions = {}

    def _sanitize_dimensions(self, item):
        field = self.data_source._determine_fields(item)[0]
        finfo = self.data_source.ds.field_info[field]
        dimensions = Unit(
            finfo.units, registry=self.data_source.ds.unit_registry).dimensions
        if dimensions not in self.known_dimensions:
            self.known_dimensions[dimensions] = item
            ret_item = item
        else:
            ret_item = self.known_dimensions[dimensions]
        return ret_item

    def __getitem__(self, item):
        ret_item = self._sanitize_dimensions(item)
        return super(LinePlotDictionary, self).__getitem__(ret_item)

    def __setitem__(self, item, value):
        ret_item = self._sanitize_dimensions(item)
        super(LinePlotDictionary, self).__setitem__(ret_item, value)

    def __contains__(self, item):
        ret_item = self._sanitize_dimensions(item)
        return super(LinePlotDictionary, self).__contains__(ret_item)

class LinePlot(PlotContainer):
    r"""
    A class for constructing line plots

    Parameters
    ----------

    ds : :class:`yt.data_objects.static_output.Dataset`
        This is the dataset object corresponding to the
        simulation output to be plotted.
    fields : string / tuple, or list of strings / tuples
        The name(s) of the field(s) to be plotted.
    start_point : n-element list, tuple, ndarray, or YTArray
        Contains the coordinates of the first point for constructing the line.
        Must contain n elements where n is the dimensionality of the dataset.
    end_point : n-element list, tuple, ndarray, or YTArray
        Contains the coordinates of the first point for constructing the line.
        Must contain n elements where n is the dimensionality of the dataset.
    npoints : int
        How many points to sample between start_point and end_point for
        constructing the line plot
    figure_size : int or two-element iterable of ints
        Size in inches of the image.
        Default: 5 (5x5)
    fontsize : int
        Font size for all text in the plot.
        Default: 14
    labels : dictionary
        Keys should be the field names. Values should be latex-formattable
        strings used in the LinePlot legend
        Default: None


    Example
    -------

    >>> import yt
    >>>
    >>> ds = yt.load('IsolatedGalaxy/galaxy0030/galaxy0030')
    >>>
    >>> plot = yt.LinePlot(ds, 'density', [0, 0, 0], [1, 1, 1], 512)
    >>> plot.add_legend('density')
    >>> plot.set_x_unit('cm')
    >>> plot.set_unit('density', 'kg/cm**3')
    >>> plot.save()

    """
    _plot_type = 'line_plot'

    def __init__(self, ds, fields, start_point, end_point, npoints,
                 figure_size=5., fontsize=14., labels=None):
        """
        Sets up figure and axes
        """
        self.start_point = _validate_point(start_point, ds, start=True)
        self.end_point = _validate_point(end_point, ds)
        self.npoints = npoints

        self._initialize_instance(self, ds, fields, figure_size, fontsize)

        if labels is None:
            self.labels = {}
        else:
            self.labels = labels
        for f in self.fields:
            if f not in self.labels:
                self.labels[f] = f[1]

        self._setup_plots()

    @classmethod
    def _initialize_instance(cls, obj, ds, fields, figure_size=5., fontsize=14.):
        obj._x_unit = None
        obj._y_units = {}
        obj._titles = {}

        data_source = ds.all_data()

        obj.fields = data_source._determine_fields(fields)
        obj.plots = LinePlotDictionary(data_source)
        obj.include_legend = defaultdict(bool)
        super(LinePlot, obj).__init__(data_source, figure_size, fontsize)
        for f in obj.fields:
            finfo = obj.data_source.ds._get_field_info(*f)
            if finfo.take_log:
                obj._field_transform[f] = log_transform
            else:
                obj._field_transform[f] = linear_transform

    @classmethod
    def from_lines(cls, ds, fields, lines, figure_size=5., font_size=14.):
        """
        A class method for constructing a line plot from multiple sampling lines

        Parameters
        ----------

        ds : :class:`yt.data_objects.static_output.Dataset`
            This is the dataset object corresponding to the
            simulation output to be plotted.
        fields : string / tuple, or list of strings / tuples
            The name(s) of the field(s) to be plotted.
        figure_size : int or two-element iterable of ints
            Size in inches of the image.
            Default: 5 (5x5)
        fontsize : int
            Font size for all text in the plot.
            Default: 14
        """
        obj = cls.__new__(cls)
        cls._initialize_instance(obj, ds, fields, figure_size, font_size)

        for line in lines:
            dimensions_counter = defaultdict(int)
            for field in obj.fields:
                finfo = obj.ds.field_info[field]
                dimensions = Unit(finfo.units,
                                  registry=obj.ds.unit_registry).dimensions
                dimensions_counter[dimensions] += 1

            for field in obj.fields:
                plot = obj._get_plot_instance(field)
                x, y = obj.ds.coordinates.pixelize_line(
                    field, line.start_point, line.end_point, line.npoints)
                finfo = obj.ds.field_info[field]
                dimensions = Unit(finfo.units,
                                  registry=obj.ds.unit_registry).dimensions
                if dimensions_counter[dimensions] > 1:
                    legend_label = r"$%s;$ %s" % (line.label, finfo.get_latex_display_name())
                else:
                    legend_label = r"$%s$" % line.label
                obj._plot_xy(field, plot, x, y, dimensions_counter, legend_label=legend_label)
                plot.axes.legend()
        obj._plot_valid = True
        return obj

    def _get_plot_instance(self, field):
        fontscale = self._font_properties._size / 14.
        top_buff_size = 0.35*fontscale

        x_axis_size = 1.35*fontscale
        y_axis_size = 0.7*fontscale
        right_buff_size = 0.2*fontscale

        if iterable(self.figure_size):
            figure_size = self.figure_size
        else:
            figure_size = (self.figure_size, self.figure_size)

        xbins = np.array([x_axis_size, figure_size[0],
                          right_buff_size])
        ybins = np.array([y_axis_size, figure_size[1], top_buff_size])

        size = [xbins.sum(), ybins.sum()]

        x_frac_widths = xbins/size[0]
        y_frac_widths = ybins/size[1]

        axrect = (
            x_frac_widths[0],
            y_frac_widths[0],
            x_frac_widths[1],
            y_frac_widths[1],
        )

        try:
            plot = self.plots[field]
        except KeyError:
            plot = PlotMPL(self.figure_size, axrect, None, None)
            self.plots[field] = plot
        return plot

    def _plot_xy(self, field, plot, x, y, dimensions_counter, legend_label=None):
        if self._x_unit is None:
            unit_x = x.units
        else:
            unit_x = self._x_unit

        if field in self._y_units:
            unit_y = self._y_units[field]
        else:
            unit_y = y.units

        x = x.to(unit_x)
        y = y.to(unit_y)

        plot.axes.plot(x, y, label=legend_label)

        if self._field_transform[field] != linear_transform:
            if (y < 0).any():
                plot.axes.set_yscale('symlog')
            else:
                plot.axes.set_yscale('log')

        plot._set_font_properties(self._font_properties, None)

        axes_unit_labels = self._get_axes_unit_labels(unit_x, unit_y)

        finfo = self.ds.field_info[field]

        x_label = r'$\rm{Path\ Length' + axes_unit_labels[0]+'}$'

        finfo = self.ds.field_info[field]
        dimensions = Unit(finfo.units,
                          registry=self.ds.unit_registry).dimensions
        if dimensions_counter[dimensions] > 1:
            y_label = (r'$\rm{Multiple\ Fields}$' + r'$\rm{' +
                       axes_unit_labels[1]+'}$')
        else:
            y_label = (finfo.get_latex_display_name() + r'$\rm{' +
                       axes_unit_labels[1]+'}$')

        plot.axes.set_xlabel(x_label)
        plot.axes.set_ylabel(y_label)

        if field in self._titles:
            plot.axes.set_title(self._titles[field])


    def _setup_plots(self):
        if self._plot_valid is True:
            return
        for plot in self.plots.values():
            plot.axes.cla()
        dimensions_counter = defaultdict(int)
        for field in self.fields:
            finfo = self.ds.field_info[field]
            dimensions = Unit(finfo.units,
                              registry=self.ds.unit_registry).dimensions
            dimensions_counter[dimensions] += 1
        for field in self.fields:
            plot = self._get_plot_instance(field)

            x, y = self.ds.coordinates.pixelize_line(
                field, self.start_point, self.end_point, self.npoints)

            self._plot_xy(field, plot, x, y, dimensions_counter,
                          legend_label=self.labels[field])

            if self.include_legend[field]:
                plot.axes.legend()


    @invalidate_plot
    def annotate_legend(self, field):
        """Adds a legend to the `LinePlot` instance"""
        self.include_legend[field] = True

    @invalidate_plot
    def set_x_unit(self, unit_name):
        """Set the unit to use along the x-axis

        Parameters
        ----------
        unit_name: str
          The name of the unit to use for the x-axis unit
        """
        self._x_unit = unit_name

    @invalidate_plot
    def set_unit(self, field, unit_name):
        """Set the unit used to plot the field

        Parameters
        ----------
        field: str or field tuple
           The name of the field to set the units for
        unit_name: str
           The name of the unit to use for this field
        """
        self._y_units[self.data_source._determine_fields(field)[0]] = unit_name

    @invalidate_plot
    def annotate_title(self, field, title):
        """Set the unit used to plot the field

        Parameters
        ----------
        field: str or field tuple
           The name of the field to set the units for
        title: str
           The title to use for the plot
        """
        self._titles[self.data_source._determine_fields(field)[0]] = title

def _validate_point(point, ds, start=False):
    if not iterable(point):
        raise RuntimeError(
            "Input point must be array-like"
        )
    if not isinstance(point, YTArray):
        point = ds.arr(point, 'code_length')
    if len(point.shape) != 1:
        raise RuntimeError(
            "Input point must be a 1D array"
        )
    if point.shape[0] < ds.dimensionality:
        raise RuntimeError(
            "Input point must have an element for each dimension"
        )
    # need to pad to 3D elements to avoid issues later
    if point.shape[0] < 3:
        if start:
            val = 0
        else:
            val = 1
        point = np.append(point.d, [val]*(3-ds.dimensionality))*point.uq
    return point
