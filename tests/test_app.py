import os
import unittest

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

    def test_public_submission_is_quarantined_from_slides(self):
        with app.app_context():
            curated = create_category("Quotes")
            create_quote("A curated quote", "Curator", curated.id)

        response = self.client.post(
            "/submit",
            data={"text": "A pending quote", "author": "Visitor"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"submitted for review", response.data)

        slides = self.client.get("/quotes_carousel")
        self.assertIn(b"A curated quote", slides.data)
        self.assertNotIn(b"A pending quote", slides.data)

        with app.app_context():
            pending = Category.query.filter_by(name="Pending Review").one()
            quote = Quote.query.filter_by(text="A pending quote").one()
            self.assertEqual(quote.category_id, pending.id)

    def test_admin_can_publish_a_pending_quote(self):
        self.client.post(
            "/submit",
            data={"text": "Publish me", "author": "Visitor"},
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


if __name__ == "__main__":
    unittest.main()
