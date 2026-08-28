//! Port of `hreflex.tokenizer` (the pure-Python reference implementation).
//! Same algorithm, same correctness invariants -- only the primitives
//! change: `memchr`/`memchr3` (SIMD byte search) instead of Python's `re`,
//! and the whole document is scanned in one call instead of one
//! `re.search` per tag.
//!
//! The load-bearing invariant, ported unchanged from `tokenizer.py`: if a
//! tag or a quoted attribute value is ever left unterminated, the WHATWG
//! tokenizer state machine treats everything from that point to EOF as
//! belonging to it -- so `find_tag_end` returning `None` means "stop the
//! whole scan," not "skip this tag and keep going." That's simultaneously
//! spec-correct and what keeps this O(n) instead of the O(n^2) the
//! Python version was measured to hit before that rule was enforced.

use memchr::{memchr, memchr3};

const RAW_TEXT_TAGS: [&str; 4] = ["script", "style", "textarea", "title"];

enum Opener {
    Comment(usize),
    Cdata(usize),
    RawText(&'static str, usize),
    Anchor(usize),
}

fn is_tag_name_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

fn is_attr_name_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_' || b == b'-'
}

fn eq_ci(a: u8, b: u8) -> bool {
    a.to_ascii_lowercase() == b.to_ascii_lowercase()
}

fn matches_ci(bytes: &[u8], pos: usize, needle: &[u8]) -> bool {
    pos + needle.len() <= bytes.len()
        && bytes[pos..pos + needle.len()]
            .iter()
            .zip(needle)
            .all(|(&a, &b)| eq_ci(a, b))
}

/// Find the next opener at or after `from`. Any `<` that doesn't start one
/// of our five recognized constructs is just data (e.g. `<div>`, a stray
/// `<` in prose) and is skipped, not a failure.
fn find_opener(bytes: &[u8], from: usize) -> Option<Opener> {
    let len = bytes.len();
    let mut i = from;
    loop {
        let start = i + memchr(b'<', &bytes[i..])?;

        if matches_ci(bytes, start, b"<!--") {
            return Some(Opener::Comment(start + 4));
        }
        if matches_ci(bytes, start, b"<![CDATA[") {
            return Some(Opener::Cdata(start + 9));
        }
        let mut matched = None;
        for &tag in RAW_TEXT_TAGS.iter() {
            let tag_bytes = tag.as_bytes();
            if matches_ci(bytes, start + 1, tag_bytes) {
                let after = start + 1 + tag_bytes.len();
                if !(after < len && is_tag_name_byte(bytes[after])) {
                    matched = Some(Opener::RawText(tag, after));
                    break;
                }
            }
        }
        if matched.is_none() && matches_ci(bytes, start + 1, b"a") {
            let after = start + 2;
            if !(after < len && is_tag_name_byte(bytes[after])) {
                matched = Some(Opener::Anchor(after));
            }
        }
        if let Some(opener) = matched {
            return Some(opener);
        }

        i = start + 1;
        if i >= len {
            return None;
        }
    }
}

/// Index of the unquoted '>' closing the tag whose body starts at `pos`,
/// or `None` if the document runs out first. O(distance scanned): jumps
/// via memchr3/memchr, never backtracks, never rescans a byte twice.
fn find_tag_end(bytes: &[u8], pos: usize) -> Option<usize> {
    let mut i = pos;
    loop {
        let at = i + memchr3(b'>', b'"', b'\'', &bytes[i..])?;
        match bytes[at] {
            b'>' => return Some(at),
            quote => {
                let close = at + 1 + memchr(quote, &bytes[at + 1..])?;
                i = close + 1;
            }
        }
    }
}

/// Find `</tagname\s*>` (case-insensitive) at or after `from`. Per spec,
/// raw-text elements don't nest, so the first match wins; a stray `<`
/// that isn't this exact close tag is just raw-text content and is
/// skipped, same skip-and-continue shape as `find_opener`.
fn find_raw_text_close(bytes: &[u8], tag: &str, from: usize) -> Option<usize> {
    let tag_bytes = tag.as_bytes();
    let len = bytes.len();
    let mut i = from;
    loop {
        let start = i + memchr(b'<', &bytes[i..])?;
        if start + 1 < len
            && bytes[start + 1] == b'/'
            && matches_ci(bytes, start + 2, tag_bytes)
        {
            let mut j = start + 2 + tag_bytes.len();
            while j < len && bytes[j].is_ascii_whitespace() {
                j += 1;
            }
            if j < len && bytes[j] == b'>' {
                return Some(j + 1);
            }
        }
        i = start + 1;
        if i >= len {
            return None;
        }
    }
}

/// Extract the value of the `href` attribute from a tag body (the slice
/// between the tag name and its closing '>', which by construction from
/// `find_tag_end` never itself contains an unquoted '>'). The negative
/// boundary check before "href" matters: without it, "href" matches
/// *inside* `data-original-href=` or `originalHref=` too, which is a real
/// bug the pure-Python version shipped with (fixed there in the same
/// commit that added this port).
fn extract_href(tag_body: &str) -> Option<&str> {
    let bytes = tag_body.as_bytes();
    let len = bytes.len();
    let mut i = 0;
    while i < len {
        if matches_ci(bytes, i, b"href") && (i == 0 || !is_attr_name_byte(bytes[i - 1])) {
            let mut j = i + 4;
            while j < len && bytes[j].is_ascii_whitespace() {
                j += 1;
            }
            if j < len && bytes[j] == b'=' {
                j += 1;
                while j < len && bytes[j].is_ascii_whitespace() {
                    j += 1;
                }
                if j < len && (bytes[j] == b'"' || bytes[j] == b'\'') {
                    let quote = bytes[j];
                    let start = j + 1;
                    let end = match memchr(quote, &bytes[start..]) {
                        Some(rel) => start + rel,
                        None => len,
                    };
                    return Some(&tag_body[start..end]);
                } else if j < len {
                    let start = j;
                    let mut k = j;
                    while k < len {
                        let c = bytes[k];
                        if c.is_ascii_whitespace()
                            || matches!(c, b'\'' | b'"' | b'=' | b'<' | b'>' | b'`')
                        {
                            break;
                        }
                        k += 1;
                    }
                    return Some(&tag_body[start..k]);
                }
            }
        }
        i += 1;
    }
    None
}

pub fn extract_links(html: &str) -> Vec<String> {
    let mut out = Vec::new();

    let bytes = html.as_bytes();
    let len = bytes.len();
    let mut pos = 0usize;

    while pos < len {
        let opener = match find_opener(bytes, pos) {
            Some(o) => o,
            None => break,
        };

        match opener {
            Opener::Comment(start) => match find_sub(bytes, start, b"-->") {
                Some(end) => pos = end + 3,
                None => break,
            },
            Opener::Cdata(start) => match find_sub(bytes, start, b"]]>") {
                Some(end) => pos = end + 3,
                None => break,
            },
            Opener::RawText(tag, attrs_start) => {
                let tag_end = match find_tag_end(bytes, attrs_start) {
                    Some(i) => i,
                    None => break,
                };
                match find_raw_text_close(bytes, tag, tag_end + 1) {
                    Some(after_close) => pos = after_close,
                    None => break,
                }
            }
            Opener::Anchor(attrs_start) => {
                let tag_end = match find_tag_end(bytes, attrs_start) {
                    Some(i) => i,
                    None => break,
                };
                if let Some(href) = extract_href(&html[attrs_start..tag_end]) {
                    let decoded = html_escape::decode_html_entities(href);
                    out.push(decoded.into_owned());
                }
                pos = tag_end + 1;
            }
        }
    }

    out
}

fn find_sub(bytes: &[u8], from: usize, needle: &[u8]) -> Option<usize> {
    memchr::memmem::find(&bytes[from..], needle).map(|rel| from + rel)
}

#[cfg(test)]
mod tests {
    use super::extract_links;
    use std::time::Instant;

    #[test]
    fn basic_and_quoting_styles() {
        let html = r#"<a href="/dq">x</a><a href='/sq'>x</a><a href=/bare>x</a>"#;
        assert_eq!(extract_links(html), vec!["/dq", "/sq", "/bare"]);
    }

    #[test]
    fn href_inside_script_is_not_extracted() {
        let html = r#"<script>var s = "<a href=\"/evil\">";</script><a href="/real">x</a>"#;
        assert_eq!(extract_links(html), vec!["/real"]);
    }

    #[test]
    fn unterminated_script_consumes_to_eof() {
        let html = r#"<script>var x = "<a href=\"/evil\">""#;
        assert!(extract_links(html).is_empty());
    }

    #[test]
    fn base_tag_is_inert_plain_data() {
        // <base> is no longer special-cased -- no resolution happens, so
        // there is nothing for a <base href> to change. It should be
        // skipped like any other non-<a> tag, with no effect on the <a>
        // that follows.
        let html = r#"<base href="https://example.com/"><a href="x">x</a>"#;
        assert_eq!(extract_links(html), vec!["x"]);
    }

    #[test]
    fn href_boundary_guard_rejects_hyphenated_attribute() {
        let html = r#"<a data-original-href="/wrong" href="/right">x</a>"#;
        assert_eq!(extract_links(html), vec!["/right"]);
    }

    #[test]
    fn adversarial_no_closing_angle_bracket_stays_linear() {
        let html = "<a ".repeat(200_000);
        let start = Instant::now();
        assert!(extract_links(&html).is_empty());
        assert!(start.elapsed().as_secs_f64() < 1.0);
    }
}
