This is the g2ana module, part of the Gen2 Observation Control System. 

It provides the client program for receiving data from the Gen2 data
transfer system.  This package is necessary for a site to participate as
a local or remote analysis site.

## Dependencies

* Requires `g2cam` package from naojsoft.

* Optional: `naojutils` package from naojsoft.

### `fitsview` is required but not declared

**`anaview` will not start unless `fitsview` is installed**, and nothing in
`pyproject.toml` says so.

`anaview` loads its ObsLog and `QL_*` plugins out of the `fitsview` package
rather than carrying copies of them.  They are the same plugins the summit
viewer runs; the only thing that differs between the two sites is where a
frame the log has never displayed is read from, and ObsLog asks its
`loader_plugin` setting about that.  The ANA plugin names itself there, so
there is nothing to configure -- but there is also nothing for `anaview` to
fall back on if `fitsview` is missing.

It is left undeclared on purpose: `fitsview` is deployed to the analysis
hosts by the same process that deploys this, not resolved by `pip`, and
naming it as a dependency would have `pip` try to fetch a package that is
not published.  When setting up a new host, install `fitsview` yourself.

## Installation

It is recommended that you install a virtual (miniconda, virtualenv,
etc) environment to run the software in with related dependencies.

Activate this environment and then:

```bash
$ pip install .
```


