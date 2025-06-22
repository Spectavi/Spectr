import logging

log = logging.getLogger(__name__)

def apply_patch():
    try:
        import plotext._monitor as _monitor
        import plotext._utility as ut
    except Exception as exc:
        log.debug("plotext not available, skipping patch: %s", exc)
        return

    def draw_bar(self, *args, marker=None, color=None, fill=None, width=None,
                 orientation=None, minimum=None, offset=None, reset_ticks=None,
                 xside=None, yside=None, label=None):
        x, y = ut.set_data(*args)
        marker = self.default.bar_marker if marker is None else marker
        fill = self.default.bar_fill if fill is None else fill
        width = self.default.bar_width if width is None else width
        width = 1 if width > 1 else 0 if width < 0 else width
        orientation = self.check_orientation(orientation, 1)
        minimum = 0 if minimum is None else minimum
        offset = 0 if offset is None else offset
        reset_ticks = True if reset_ticks is None else reset_ticks

        x_string = any([type(el) == str for el in x])
        l = len(x)
        xticks = range(1, l + 1) if x_string else x
        xlabels = x if x_string else map(str, x)
        x = xticks if x_string else x
        x = [el + offset for el in x]
        xbar, ybar = ut.bars(x, y, width, minimum)
        xbar, ybar = [xbar, ybar] if orientation[0] == 'v' else [ybar, xbar]
        if reset_ticks:
            if orientation[0] == 'v':
                self.set_xticks(xticks, xlabels, xside)
            else:
                self.set_yticks(xticks, xlabels, yside)

        firstbar = min([b for b in range(len(x)) if ybar[b][1] != 0], default=0)

        for b in range(len(x)):
            xb = xbar[b]; yb = ybar[b]
            plot_label = label if b == firstbar else None
            plot_color = color[b]
            nobar = (yb[1] == 0 and orientation[0] == 'v') or (xb[1] == 0 and orientation[0] == 'h')
            plot_marker = " " if nobar else marker
            self.draw_rectangle(
                xb,
                yb,
                xside=xside,
                yside=yside,
                lines=True,
                marker=plot_marker,
                color=plot_color,
                fill=fill,
                label=plot_label,
            )

    _monitor.monitor_class.draw_bar = draw_bar
