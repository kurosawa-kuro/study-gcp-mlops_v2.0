"""Playwright smoke tests — 3 ページのレンダリング + /predict のフロントエンド連携."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestIndexPage:
    def test_renders_predict_form(self, page: Page) -> None:
        page.goto("/")
        expect(page).to_have_title(re.compile(r"Predict"))
        expect(page.locator("h1")).to_have_text("Predict")
        # 特徴量 8 つの input が出ていること (schema.FEATURE_COLS)
        for col in (
            "MedInc", "HouseAge", "AveRooms", "AveBedrms",
            "Population", "AveOccup", "Latitude", "Longitude",
        ):
            expect(page.locator(f"input#{col}")).to_be_visible()

    def test_nav_links_present(self, page: Page) -> None:
        page.goto("/")
        expect(page.locator("a.nav-link[href='/']")).to_be_visible()
        expect(page.locator("a.nav-link[href='/metrics']")).to_be_visible()
        expect(page.locator("a.nav-link[href='/data']")).to_be_visible()

    def test_submit_shows_predicted_price(self, page: Page) -> None:
        page.goto("/")
        page.locator("button.ml-btn[type='submit']").click()
        # JS が /predict を叩いて #price を更新するまで待つ (デフォルト値送信)
        price_text = page.locator("#price")
        expect(price_text).to_contain_text("$", timeout=5000)
        expect(page.locator("#unit")).to_contain_text("raw value:")


class TestMetricsPage:
    def test_renders(self, page: Page) -> None:
        page.goto("/metrics")
        expect(page).to_have_title(re.compile(r"Metrics"))
        expect(page.locator("h1")).to_have_text("Model Metrics")


class TestDataPage:
    def test_renders_without_db(self, page: Page) -> None:
        # PostgreSQL は起動していないので dataset.load で例外が出るが、
        # 画面側は空状態で描画されることを確認する (main.py の try/except)
        page.goto("/data")
        expect(page).to_have_title(re.compile(r"Data"))
        expect(page.locator("h1")).to_have_text("Training Data")
