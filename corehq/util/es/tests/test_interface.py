import uuid

from contextlib import contextmanager
from django.test import SimpleTestCase
from mock import patch

from corehq.apps.es.tests.utils import es_test
from corehq.elastic import get_es_new
from corehq.util.es.interface import ElasticsearchInterface
from corehq.util.es.tests.util import (
    TEST_ES_ALIAS,
    TEST_ES_MAPPING,
    TEST_ES_TYPE,
    deregister_test_meta,
    register_test_meta,
)


@es_test
class TestESInterface(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        register_test_meta()
        cls.index = TEST_ES_ALIAS
        cls.doc_type = TEST_ES_TYPE
        cls.es = get_es_new()
        meta = {"mapping": TEST_ES_MAPPING}
        if not cls.es.indices.exists(cls.index):
            cls.es.indices.create(index=cls.index, body=meta)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.es.indices.delete(cls.index)
        deregister_test_meta()

    def _validate_es_scroll_search_params(self, scroll_query, search_query):
        """Call ElasticsearchInterface.iter_scroll() and test that the resulting
        API search parameters match what we expect.

        Notably:
        - Search call does not include the `search_type='scan'`.
        - Calling `iter_scroll(..., body=scroll_query)` results in an API call
          where `body == search_query`.
        """
        interface = ElasticsearchInterface(self.es)
        scroll_kw = {
            "doc_type": self.doc_type,
            "params": {},
            "scroll": "1m",
            "size": 10,
        }
        with patch.object(self.es, "search", return_value={}) as search:
            list(interface.iter_scroll(self.index, body=scroll_query, **scroll_kw))
            search.assert_called_once_with(index=self.index, body=search_query, **scroll_kw)

    def test_scroll_no_searchtype_scan(self):
        """Tests that search_type='scan' is not added to the search parameters"""
        self._validate_es_scroll_search_params({}, {"sort": "_doc"})

    def test_scroll_query_extended(self):
        """Tests that sort=_doc is added to an non-empty query"""
        self._validate_es_scroll_search_params({"_id": "abc"},
                                             {"_id": "abc", "sort": "_doc"})

    def test_scroll_query_sort_safe(self):
        """Tests that a provided a `sort` query will not be overwritten"""
        self._validate_es_scroll_search_params({"sort": "_id"}, {"sort": "_id"})

    def test_search_and_scroll_yield_same_docs(self):
        # some documents for querying
        docs = [
            {"prop": "centerline", "prop_count": 1},
            {"prop": "starboard", "prop_count": 2},
        ]
        with self._index_test_docs(self.index, self.doc_type, docs) as indexed:

            def search_query():
                """Perform a search query"""
                return interface.search(self.index, self.doc_type)["hits"]["hits"]

            def scroll_query():
                """Perform a scroll query"""
                for results in interface.iter_scroll(self.index, self.doc_type):
                    for hit in results["hits"]["hits"]:
                        yield hit

            interface = ElasticsearchInterface(self.es)
            for results_getter in [search_query, scroll_query]:
                results = {}
                for hit in results_getter():
                    results[hit["_id"]] = hit
                self.assertEqual(len(indexed), len(results))
                for doc_id, doc in indexed.items():
                    self.assertIn(doc_id, results)
                    self.assertEqual(self.doc_type, results[doc_id]["_type"])
                    for attr in doc:
                        self.assertEqual(doc[attr], results[doc_id]["_source"][attr])

    @contextmanager
    def _index_test_docs(self, index, doc_type, docs):
        interface = ElasticsearchInterface(self.es)
        indexed = {}
        for doc in docs:
            doc_id = doc.get("_id")
            if doc_id is None:
                doc = dict(doc)  # make a copy
                doc_id = doc["_id"] = uuid.uuid4().hex
            indexed[doc_id] = doc
            interface.index_doc(index, doc_type, doc_id, doc,
                                params={"refresh": True})
        try:
            yield indexed
        finally:
            for doc_id in indexed:
                self.es.delete(index, doc_type, doc_id)
