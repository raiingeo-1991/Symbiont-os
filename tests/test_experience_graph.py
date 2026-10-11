import unittest

from core.experience_graph import ExperienceGraph


class ExperienceGraphTests(unittest.TestCase):

    def setUp(self):
        self.graph = ExperienceGraph()

    def test_add_and_get_node(self):
        node_id = self.graph.add_node(
            "Работа ночью",
            node_type="experience",
            metadata={"source": "owner"},
        )

        node = self.graph.get_node(node_id)

        self.assertIsNotNone(node)
        self.assertEqual(node.content, "Работа ночью")
        self.assertEqual(node.node_type, "experience")
        self.assertEqual(
            node.metadata["source"],
            "owner",
        )

    def test_stable_id_update(self):
        node_id = self.graph.add_node(
            "Первое содержание",
            node_id="fixed-1",
        )

        same_id = self.graph.add_node(
            "Обновлённое содержание",
            node_id="fixed-1",
        )

        self.assertEqual(node_id, same_id)
        self.assertEqual(
            self.graph.get_node(
                "fixed-1"
            ).content,
            "Обновлённое содержание",
        )

        self.assertEqual(
            self.graph.status()["nodes"],
            1,
        )

    def test_add_edge_and_related(self):
        a = self.graph.add_node(
            "Работа ночью",
            node_type="experience",
        )
        b = self.graph.add_node(
            "Тишина",
            node_type="context",
        )

        self.assertTrue(
            self.graph.add_edge(
                a,
                b,
                relation="context",
                weight=0.8,
            )
        )

        related = self.graph.related(a)

        self.assertEqual(len(related), 1)
        self.assertEqual(
            related[0][1].node_id,
            b,
        )
        self.assertEqual(
            related[0][0].relation,
            "context",
        )

    def test_incoming_and_outgoing(self):
        a = self.graph.add_node("A")
        b = self.graph.add_node("B")

        self.graph.add_edge(
            a,
            b,
            relation="causes",
        )

        outgoing = self.graph.related(
            a,
            direction="out",
        )
        incoming = self.graph.related(
            b,
            direction="in",
        )

        self.assertEqual(
            outgoing[0][1].node_id,
            b,
        )
        self.assertEqual(
            incoming[0][1].node_id,
            a,
        )

    def test_read_context(self):
        a = self.graph.add_node("Работа")
        b = self.graph.add_node("Ночь")
        c = self.graph.add_node("Тишина")

        self.graph.add_edge(a, b, "context")
        self.graph.add_edge(b, c, "context")

        context = self.graph.read_context(
            a,
            depth=2,
        )

        context_ids = {
            node.node_id
            for node in context
        }

        self.assertIn(b, context_ids)
        self.assertIn(c, context_ids)

    def test_nodes_by_type(self):
        self.graph.add_node(
            "Работа",
            node_type="experience",
        )
        self.graph.add_node(
            "Ночь",
            node_type="context",
        )
        self.graph.add_node(
            "Тишина",
            node_type="context",
        )

        contexts = self.graph.nodes_by_type(
            "context"
        )

        self.assertEqual(len(contexts), 2)

    def test_duplicate_edge_does_not_create_second_edge(self):
        a = self.graph.add_node("A")
        b = self.graph.add_node("B")

        self.graph.add_edge(
            a,
            b,
            relation="related",
            weight=0.5,
        )

        self.graph.add_edge(
            a,
            b,
            relation="related",
            weight=0.9,
        )

        self.assertEqual(
            self.graph.status()["edges"],
            1,
        )

        related = self.graph.related(a)

        self.assertAlmostEqual(
            related[0][0].weight,
            0.9,
        )

    def test_capacity(self):
        graph = ExperienceGraph(capacity=1)

        graph.add_node("one")

        with self.assertRaises(MemoryError):
            graph.add_node("two")


if __name__ == "__main__":
    unittest.main()
