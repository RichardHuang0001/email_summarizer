#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

from email_summarizer.tools.email_reader import EmailReaderTool


class DummyClient:
    def __init__(self, fail_batch=False, fail_single_uids=None):
        self.fail_batch = fail_batch
        self.fail_single_uids = set(fail_single_uids or [])

    def fetch(self, uids, data_items):
        if self.fail_batch and len(uids) > 1:
            raise AssertionError("unknown status keyword 'e' in marked section")

        uid = uids[0]
        if uid in self.fail_single_uids:
            raise AssertionError("unknown status keyword 'e' in marked section")

        return {uid: {data_items[0]: b"ok"}}


def test_fetch_with_fallback_normal_batch():
    client = DummyClient(fail_batch=False)
    out = EmailReaderTool._fetch_with_fallback(client, [1, 2], [b"ENVELOPE"], "test")

    assert 1 in out


def test_fetch_with_fallback_degrades_to_single():
    client = DummyClient(fail_batch=True)
    out = EmailReaderTool._fetch_with_fallback(client, [1, 2], [b"ENVELOPE"], "test")

    assert 1 in out
    assert 2 in out


def test_fetch_with_fallback_skips_bad_single_uid():
    client = DummyClient(fail_batch=True, fail_single_uids={2})
    out = EmailReaderTool._fetch_with_fallback(client, [1, 2], [b"ENVELOPE"], "test")

    assert 1 in out
    assert 2 not in out


def test_safe_html_to_text_handles_marked_section_assertion():
    tool = EmailReaderTool()

    bad_html = "<![endif]><p>Hello World</p>"
    out = EmailReaderTool._safe_html_to_text(tool, bad_html)

    assert "Hello World" in out
