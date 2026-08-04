import os
import unittest
from unittest.mock import patch

os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"

from app import Category, Quote, app, create_category, create_quote, db  # noqa: E402


class TextrRoutesTest(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SESSION_COOKIE_SECURE=False)
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self):
        return self.client.post(
            "/admin/login",
            data={"token": "test-admin-token"},
            follow_redirects=False,
        )

    def test_admin_routes_require_login(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

        response = self.client.get("/quote/new")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

    def test_header_brand_uses_home_and_omits_slides_link(self):
        response = self.client.get("/quotes_carousel")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="navbar-brand" href="/"', response.data)
        self.assertNotIn(b">Slides</a>", response.data)

    def test_public_submission_is_quarantined_from_slides(self):
        with app.app_context():
            curated = create_category("Quotes")
            create_quote("A curated quote", "Curator", curated.id)

        response = self.client.post(
            "/submit",
            data={"content_type": "quotes", "text": "A pending quote", "author": "Visitor"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sent for review", response.data)

        slides = self.client.get("/quotes_carousel")
        self.assertIn(b"A curated quote", slides.data)
        self.assertNotIn(b"A pending quote", slides.data)

        with app.app_context():
            pending = Category.query.filter_by(name="Pending Review - Quotes").one()
            quote = Quote.query.filter_by(text="A pending quote").one()
            self.assertEqual(quote.category_id, pending.id)

    def test_admin_can_publish_a_pending_quote(self):
        self.client.post(
            "/submit",
            data={"content_type": "quotes", "text": "Publish me", "author": "Visitor"},
        )
        with app.app_context():
            curated = create_category("Quotes")
            quote = Quote.query.filter_by(text="Publish me").one()
            quote_id = quote.id
            curated_id = curated.id

        login = self.login()
        self.assertEqual(login.status_code, 302)
        self.assertTrue(login.headers["Location"].endswith("/admin"))

        response = self.client.post(
            f"/quote/edit/{quote_id}",
            data={"text": "Publish me", "author": "Visitor", "category": curated_id},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        slides = self.client.get("/quotes_carousel")
        self.assertIn(b"Publish me", slides.data)

    def test_admin_can_edit_categories(self):
        with app.app_context():
            category = create_category("Original")
            category_id = category.id

        self.login()
        response = self.client.post(
            f"/category/edit/{category_id}",
            data={"name": "Renamed"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            self.assertIsNotNone(Category.query.filter_by(name="Renamed").first())

    def test_public_joke_submission_keeps_its_type_in_moderation(self):
        response = self.client.post(
            "/submit",
            data={"content_type": "jokes", "text": "A pending joke", "author": "Visitor"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        with app.app_context():
            pending = Category.query.filter_by(name="Pending Review - Jokes").one()
            joke = Quote.query.filter_by(text="A pending joke").one()
            self.assertEqual(joke.category_id, pending.id)

        slides = self.client.get("/quotes_carousel?category=jokes")
        self.assertNotIn(b"A pending joke", slides.data)

    def test_slides_include_content_types_and_controls_below_content(self):
        with app.app_context():
            quotes = create_category("Quotes")
            jokes = create_category("Jokes")
            poems = create_category("Poems")
            create_quote("Quote text", "Quote author", quotes.id)
            create_quote("Joke text", "Joke source", jokes.id)
            create_quote("Poem text", "Poem author", poems.id)

        response = self.client.get("/quotes_carousel?category=jokes")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"category": "jokes"', response.data)
        self.assertIn(b'"category": "poems"', response.data)
        self.assertLess(response.data.index(b'id="content-stage"'), response.data.index(b'id="prev"'))
        self.assertNotIn(b"Etherland words", response.data)
        self.assertNotIn(b"8 local items", response.data)
        self.assertIn(b'id="slide-progress-bar"', response.data)
        self.assertIn(b'id="slide-status" class="sr-only"', response.data)
        self.assertIn(b"await nextItem();", response.data)
        self.assertIn(b"window.setTimeout", response.data)

    def test_slides_shuffle_local_items_for_each_view(self):
        with app.app_context():
            category = create_category("Quotes")
            create_quote("First item", "One", category.id)
            create_quote("Second item", "Two", category.id)

        with patch("app.SYSTEM_RANDOM.shuffle", side_effect=lambda values: values.reverse()) as shuffle:
            response = self.client.get("/quotes_carousel")

        self.assertEqual(response.status_code, 200)
        shuffle.assert_called_once()
        self.assertLess(response.data.index(b"Second item"), response.data.index(b"First item"))

    @patch("app.fetch_external_content")
    def test_external_content_endpoint_returns_labeled_item(self, fetch_external_content):
        fetch_external_content.return_value = {
            "text": "API joke",
            "author": "JokeAPI",
            "category": "jokes",
            "source": "JokeAPI",
            "source_url": "https://jokeapi.dev/",
        }
        response = self.client.get("/api/content/random?type=jokes")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["category"], "jokes")
        fetch_external_content.assert_called_once_with("jokes")

    @patch("app.fetch_external_content")
    @patch("app.SYSTEM_RANDOM.choice", return_value="poems")
    def test_all_external_requests_choose_a_random_provider(self, choose, fetch_external_content):
        fetch_external_content.return_value = {
            "text": "API poem",
            "author": "Poet",
            "category": "poems",
            "source": "PoetryDB",
            "source_url": "https://poetrydb.org/",
        }
        response = self.client.get("/api/content/random?type=all")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["category"], "poems")
        choose.assert_called_once()
        fetch_external_content.assert_called_once_with("poems")

    def test_external_content_endpoint_rejects_unknown_type(self):
        response = self.client.get("/api/content/random?type=stories")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
