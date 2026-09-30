// Interactive plots: Vega-Lite (compiled in the browser) and Plotly. Matplotlib plots are static SVG.
Lattice.component("plot", {
  mount(el, data) {
    const box = el.querySelector(".lt-plot");
    if (data.backend === "vega") {
      if (!window.vega || !window.vegaLite) throw new Error("Vega is not loaded");
      const compiled = window.vegaLite.compile(data.spec).spec;
      const view = new window.vega.View(window.vega.parse(compiled), { renderer: "svg", container: box, hover: true });
      view.runAsync();
      return { view };
    }
    if (data.backend === "plotly") {
      if (!window.Plotly) throw new Error("Plotly is not loaded");
      window.Plotly.newPlot(box, data.spec.data, data.spec.layout, { displayModeBar: false, responsive: false });
      return { box };
    }
    return {};
  },
  show() {},
});
