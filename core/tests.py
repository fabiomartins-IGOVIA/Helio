import json

from django.test import TestCase
from rest_framework.test import APIClient

from .models import DatajudRegistro


class BackendSmokeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        DatajudRegistro.objects.create(
            ano=2025,
            grau="G1",
            processo="0000001-00.2025.8.05.0001",
            id_municipio="4278",
            municipio="SALVADOR",
            codigo_classe="[198]",
            nome_classe="Apelação Cível",
            codigo_assunto="[10437]",
            nome_assunto="Direito de Imagem",
            codigo_orgao="85085",
            nome_orgao="Órgão teste",
        )

    def test_health_check(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_datajud_endpoint_is_public(self):
        response = self.client.get("/api/datajud-registros/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_datajud_crud(self):
        payload = {
            "ano": 2026,
            "grau": "G2",
            "processo": "0000002-00.2026.8.05.0001",
            "id_municipio": "4278",
            "municipio": "SALVADOR",
            "codigo_classe": "[221]",
            "nome_classe": "Conflito de competência cível",
            "codigo_assunto": "[10654]",
            "nome_assunto": "Competência da Justiça Estadual",
            "codigo_orgao": "85085",
            "nome_orgao": "Órgão teste",
        }

        create_response = self.client.post("/api/datajud-registros/", payload, format="json")
        self.assertEqual(create_response.status_code, 201)
        record_id = create_response.json()["id"]

        put_response = self.client.put(
            f"/api/datajud-registros/{record_id}/",
            {**payload, "municipio": "FEIRA DE SANTANA"},
            format="json",
        )
        self.assertEqual(put_response.status_code, 200)
        self.assertEqual(put_response.json()["municipio"], "FEIRA DE SANTANA")

        update_response = self.client.patch(
            f"/api/datajud-registros/{record_id}/",
            {"municipio": "CAMAÇARI"},
            format="json",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["municipio"], "CAMAÇARI")

        delete_response = self.client.delete(f"/api/datajud-registros/{record_id}/")
        self.assertEqual(delete_response.status_code, 204)

    def test_openapi_schema_is_public(self):
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        schema = json.loads(response.content)
        self.assertTrue(any(tag["name"] == "Datajud" for tag in schema["tags"]))

    def test_swagger_ui_is_available(self):
        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, 200)
