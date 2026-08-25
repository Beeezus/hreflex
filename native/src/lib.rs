use pyo3::prelude::*;

mod scan;

/// Yield absolute URLs for every <a href> in html, resolved against
/// base_url (honoring an in-document <base href>, first one wins).
/// Same contract as hreflex.extract_links -- see tests/test_parity.py.
#[pyfunction]
fn extract_links(html: &str, base_url: &str) -> Vec<String> {
    scan::extract_links(html, base_url)
}

#[pymodule]
fn _hreflex_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_links, m)?)?;
    Ok(())
}
