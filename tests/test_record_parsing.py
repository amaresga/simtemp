#!/usr/bin/env python3
"""
Unit tests for simtemp binary record parsing and event logic.
Tests the user-space parsing without requiring the kernel module.

Author: Armando Mares
License: GPL-2.0
"""

import unittest
import struct
import time


# Constants matching kernel driver definitions
SIMTEMP_SAMPLE_SIZE = 16
SIMTEMP_FLAG_NEW_SAMPLE = 0x01
SIMTEMP_FLAG_THRESHOLD_CROSSED = 0x02


class SimtempSample:
    """Mock sample structure for testing"""
    def __init__(self, timestamp_ns, temp_mC, flags):
        self.timestamp_ns = timestamp_ns
        self.temp_mC = temp_mC
        self.flags = flags

    def pack(self):
        """Pack sample into binary format matching kernel struct"""
        return struct.pack('=QiI', self.timestamp_ns, self.temp_mC, self.flags)


def parse_sample(data):
    """Parse binary sample data"""
    if len(data) != SIMTEMP_SAMPLE_SIZE:
        raise ValueError(f"Invalid sample size: {len(data)}, expected {SIMTEMP_SAMPLE_SIZE}")

    timestamp_ns, temp_mC, flags = struct.unpack('=QiI', data)
    return timestamp_ns, temp_mC, flags


class TestRecordParsing(unittest.TestCase):
    """Test binary record parsing"""

    def test_valid_sample_parsing(self):
        """Test parsing a valid binary sample"""
        # Create a known sample
        timestamp = int(time.time() * 1_000_000_000)
        temp = 44123  # 44.123°C
        flags = SIMTEMP_FLAG_NEW_SAMPLE

        sample = SimtempSample(timestamp, temp, flags)
        data = sample.pack()

        # Parse it back
        parsed_ts, parsed_temp, parsed_flags = parse_sample(data)

        self.assertEqual(parsed_ts, timestamp)
        self.assertEqual(parsed_temp, temp)
        self.assertEqual(parsed_flags, flags)

    def test_sample_size_validation(self):
        """Test that invalid sample sizes are rejected"""
        with self.assertRaises(ValueError):
            parse_sample(b"short")

        with self.assertRaises(ValueError):
            parse_sample(b"x" * 20)  # Too long

    def test_negative_temperature(self):
        """Test parsing negative temperatures"""
        sample = SimtempSample(1000000, -5000, SIMTEMP_FLAG_NEW_SAMPLE)
        data = sample.pack()

        _, temp, _ = parse_sample(data)
        self.assertEqual(temp, -5000)

    def test_temperature_conversion(self):
        """Test millidegree to degree conversion"""
        test_cases = [
            (25000, 25.0),
            (44123, 44.123),
            (-5000, -5.0),
            (0, 0.0),
        ]

        for temp_mC, expected_C in test_cases:
            actual_C = temp_mC / 1000.0
            self.assertAlmostEqual(actual_C, expected_C, places=3)

    def test_timestamp_monotonicity(self):
        """Test that timestamps are monotonically increasing"""
        samples = []
        base_time = int(time.time() * 1_000_000_000)

        for i in range(10):
            ts = base_time + (i * 100_000_000)  # 100ms intervals
            samples.append(SimtempSample(ts, 25000, SIMTEMP_FLAG_NEW_SAMPLE))

        timestamps = [parse_sample(s.pack())[0] for s in samples]

        for i in range(1, len(timestamps)):
            self.assertGreater(timestamps[i], timestamps[i-1])


class TestEventLogic(unittest.TestCase):
    """Test event flag logic"""

    def test_new_sample_flag(self):
        """Test NEW_SAMPLE flag detection"""
        sample = SimtempSample(1000000, 25000, SIMTEMP_FLAG_NEW_SAMPLE)
        _, _, flags = parse_sample(sample.pack())

        self.assertTrue(flags & SIMTEMP_FLAG_NEW_SAMPLE)
        self.assertFalse(flags & SIMTEMP_FLAG_THRESHOLD_CROSSED)

    def test_threshold_crossed_flag(self):
        """Test THRESHOLD_CROSSED flag detection"""
        sample = SimtempSample(1000000, 50000, SIMTEMP_FLAG_THRESHOLD_CROSSED)
        _, _, flags = parse_sample(sample.pack())

        self.assertFalse(flags & SIMTEMP_FLAG_NEW_SAMPLE)
        self.assertTrue(flags & SIMTEMP_FLAG_THRESHOLD_CROSSED)

    def test_combined_flags(self):
        """Test combined flags"""
        combined = SIMTEMP_FLAG_NEW_SAMPLE | SIMTEMP_FLAG_THRESHOLD_CROSSED
        sample = SimtempSample(1000000, 46000, combined)
        _, _, flags = parse_sample(sample.pack())

        self.assertTrue(flags & SIMTEMP_FLAG_NEW_SAMPLE)
        self.assertTrue(flags & SIMTEMP_FLAG_THRESHOLD_CROSSED)

    def test_threshold_detection_logic(self):
        """Test threshold crossing detection logic"""
        threshold_mC = 45000

        test_cases = [
            (44000, False),  # Below threshold
            (45000, False),  # At threshold (not crossed)
            (45001, True),   # Above threshold
            (50000, True),   # Well above
        ]

        for temp_mC, should_alert in test_cases:
            crossed = temp_mC > threshold_mC
            self.assertEqual(crossed, should_alert,
                           f"temp={temp_mC}, threshold={threshold_mC}")


class TestBufferHandling(unittest.TestCase):
    """Test buffer and partial read handling"""

    def test_partial_read_detection(self):
        """Test detection of partial reads"""
        full_sample = SimtempSample(1000000, 25000, SIMTEMP_FLAG_NEW_SAMPLE)
        data = full_sample.pack()

        # Full read should succeed
        parse_sample(data)

        # Partial reads should fail
        for size in range(1, SIMTEMP_SAMPLE_SIZE):
            with self.assertRaises(ValueError):
                parse_sample(data[:size])

    def test_multiple_samples_in_buffer(self):
        """Test parsing multiple consecutive samples"""
        samples = [
            SimtempSample(1000000 + i*100000, 25000 + i*100,
                         SIMTEMP_FLAG_NEW_SAMPLE)
            for i in range(5)
        ]

        buffer = b''.join(s.pack() for s in samples)

        for i in range(5):
            offset = i * SIMTEMP_SAMPLE_SIZE
            sample_data = buffer[offset:offset + SIMTEMP_SAMPLE_SIZE]
            ts, temp, flags = parse_sample(sample_data)

            self.assertEqual(ts, 1000000 + i*100000)
            self.assertEqual(temp, 25000 + i*100)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def test_maximum_temperature(self):
        """Test maximum temperature values"""
        max_temp = 2**31 - 1  # Max signed 32-bit
        sample = SimtempSample(1000000, max_temp, SIMTEMP_FLAG_NEW_SAMPLE)

        _, temp, _ = parse_sample(sample.pack())
        self.assertEqual(temp, max_temp)

    def test_minimum_temperature(self):
        """Test minimum temperature values"""
        min_temp = -(2**31)  # Min signed 32-bit
        sample = SimtempSample(1000000, min_temp, SIMTEMP_FLAG_NEW_SAMPLE)

        _, temp, _ = parse_sample(sample.pack())
        self.assertEqual(temp, min_temp)

    def test_zero_timestamp(self):
        """Test zero timestamp (edge case)"""
        sample = SimtempSample(0, 25000, SIMTEMP_FLAG_NEW_SAMPLE)

        ts, _, _ = parse_sample(sample.pack())
        self.assertEqual(ts, 0)

    def test_struct_alignment(self):
        """Test that structure is properly packed"""
        sample = SimtempSample(0x123456789ABCDEF0, 0x12345678, 0xABCDEF01)
        data = sample.pack()

        # Verify size
        self.assertEqual(len(data), SIMTEMP_SAMPLE_SIZE)

        # Verify no padding (packed structure)
        expected_size = 8 + 4 + 4  # u64 + s32 + u32
        self.assertEqual(len(data), expected_size)

    def test_endianness_consistency(self):
        """Test that endianness is consistent"""
        sample = SimtempSample(0x0102030405060708, 0x11223344, 0x55667788)
        data = sample.pack()

        # Parse back and verify
        ts, temp, flags = parse_sample(data)
        self.assertEqual(ts, 0x0102030405060708)
        self.assertEqual(temp, 0x11223344)
        self.assertEqual(flags, 0x55667788)


def run_tests():
    """Run all unit tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestRecordParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestEventLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestBufferHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    exit(run_tests())
