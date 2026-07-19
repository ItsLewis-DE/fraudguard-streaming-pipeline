import unittest

from producer.kafka_producer import convert_paysim_row, validate_header


SAMPLE_ROW = {
    "step": "1",
    "type": "TRANSFER",
    "amount": "181.0",
    "nameOrig": "C1305486145",
    "oldbalanceOrg": "181.0",
    "newbalanceOrig": "0.0",
    "nameDest": "C553264065",
    "oldbalanceDest": "0.0",
    "newbalanceDest": "0.0",
    "isFraud": "1",
    "isFlaggedFraud": "0",
}


class PaySimProducerTest(unittest.TestCase):
    def test_event_and_label_are_separated(self) -> None:
        event, label = convert_paysim_row(SAMPLE_ROW, row_number=3)

        self.assertEqual(event["event_id"], "paysim-0000000003")
        self.assertEqual(event["event_id"], label["event_id"])
        self.assertNotIn("isFraud", event)
        self.assertNotIn("isFlaggedFraud", event)
        self.assertEqual(label["isFraud"], 1)
        self.assertEqual(label["isFlaggedFraud"], 0)

    def test_missing_column_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "isFraud"):
            validate_header([key for key in SAMPLE_ROW if key != "isFraud"])


if __name__ == "__main__":
    unittest.main()
