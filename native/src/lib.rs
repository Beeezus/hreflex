use pyo3::prelude::*;

mod scan;

/// Yield the raw `href` value of every `<a href>` in html, in document
/// order, HTML-entity decoded but otherwise untouched -- no URL
/// resolution. Same contract as hreflex.extract_links -- see
/// tests/test_parity.py.
#[pyfunction]
fn extract_links(html: &str) -> Vec<String> {
    scan::extract_links(html)
}

#[pymodule]
fn _hreflex_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_links, m)?)?;
    Ok(())
}
