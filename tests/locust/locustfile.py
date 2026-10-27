import random
from locust import HttpUser, task, between

class TeaStoreUser(HttpUser):
    """
    Simulates realistic user browsing, purchasing, and interacting with TeaStore.
    Runs against http://localhost:8080/tools.descartes.teastore.webui/
    """
    wait_time = between(1.0, 3.0)
    host = "http://localhost:8080"
    base_path = "/tools.descartes.teastore.webui"

    def on_start(self):
        # Initial visit to landing page
        self.client.get(f"{self.base_path}/", name="/")

    @task(4)
    def browse_homepage(self):
        self.client.get(f"{self.base_path}/", name="/home")

    @task(6)
    def browse_category(self):
        # TeaStore has default categories: 2 (Tea), 3 (Coffee), 4 (Herbal Tea), 5 (Mugs), 6 (Accessories)
        category_id = random.choice([2, 3, 4, 5, 6])
        page = random.randint(1, 3)
        self.client.get(
            f"{self.base_path}/category?page={page}&category={category_id}",
            name="/category"
        )

    @task(5)
    def view_product(self):
        # TeaStore has pre-populated products (ID ~ 1 to 500)
        product_id = random.randint(1, 300)
        self.client.get(
            f"{self.base_path}/product?id={product_id}",
            name="/product"
        )

    @task(2)
    def add_to_cart(self):
        product_id = random.randint(1, 300)
        self.client.post(
            f"{self.base_path}/cartAction",
            params={"addToCart": "", "productid": product_id},
            name="/cartAction[add]"
        )

    @task(2)
    def view_cart(self):
        self.client.get(f"{self.base_path}/cart", name="/cart")

    @task(1)
    def check_status(self):
        self.client.get(f"{self.base_path}/status", name="/status")

