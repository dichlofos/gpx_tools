#!/usr/bin/env python3

"""
GPX Tools

GPX Tracks merge/filtering/deduplicating tool
Written by Mikhail Veltishchev.

Kudos: Yulia Yaneeva for filtering idea and initial implementation.
"""

import typing as tp
import tqdm
import shutil
from pathlib import Path

import glob
import os
import sys
import argparse

from xml import etree
from xml.etree import ElementTree as ET
from geopy import distance as gd


_DISTANCE_THRESHOLD = 15
_SMOOTH_POINT_COUNT = 5

_NS = "http://www.topografix.com/GPX/1/1"
_GNS = {"g": _NS}


def _write_gpx(output_file_name: str, tree: ET):
    """Write formatted GPX to file"""
    print(f"Writing GPX to {output_file_name}...")
    ET.indent(tree, space="    ")
    tree.write(output_file_name, encoding="UTF-8")


def _get_elevation(point):
    elevation_elem = point.find("{*}ele")
    if elevation_elem is not None:
        return float(elevation_elem.text)
    return 0


def _get_time(point):
    time_elem = point.find("{*}time")
    if time_elem is not None:
        return time_elem.text
    return ""


def _get_track_list(output_file_name, current_directory=".") -> tp.List[str]:
    glob_path = os.path.join(current_directory, "*.gpx")
    output_path = Path(output_file_name).resolve()
    return sorted(
        file_name for file_name in glob.glob(glob_path)
        if Path(file_name).resolve() != output_path
    )


def _merge_tracks(
    left_file_name: str,
    right_file_name: str,
    output_file_name: tp.Optional[str]=None,
) -> None:
    """
    Merge `right_file_name` track data into `left_file_name` track data
    """
    if output_file_name is None:
        output_file_name = left_file_name

    print(f"Merging {left_file_name} with {right_file_name} into {output_file_name}...")

    left_tree = ET.parse(left_file_name)
    right_tree = ET.parse(right_file_name)
    left_root = left_tree.getroot()
    right_root = right_tree.getroot()

    all_left_trks = left_root.findall("g:trk", _GNS)
    if len(all_left_trks) > 1:
        raise Exception(
            f"More than one `trk` in file {left_file_name}, "
            "GPX seems to be invalid. Please report to author. "
        )

    right_segments = right_root.findall("g:trk/g:trkseg", _GNS)

    main_trk = None
    if all_left_trks:
        main_trk = all_left_trks[0]
    else:
        if right_segments:
            main_trk = ET.SubElement(left_root, "trk")

    if main_trk is not None:
        # merge tracks
        added_segments = 0
        for right_track_segment in right_segments:
            main_trk.append(right_track_segment)
            # print("  Added segment to main track")
            added_segments += 1
        if added_segments:
            print(f"Merged {added_segments} segments")
    else:
        print("No track info found")

    added_waypoints = 0
    for wpt in right_root.iterfind("g:wpt", _GNS):
        added_waypoints += 1
        left_root.append(wpt)

    if added_waypoints:
        print(f"Merged {added_waypoints} waypoints")

    _write_gpx(output_file_name, left_tree)


def _filter_duplicates(input_file_name: str, output_file_name: str=None) -> None:
    """
    Remove duplicated points from track
    """
    if output_file_name is None:
        output_file_name = input_file_name

    print(f"Filter duplicates from {input_file_name} to {output_file_name}")

    tree = ET.parse(input_file_name)
    root = tree.getroot()

    all_timestamps = set()

    point_count = 0
    removed_point_count = 0
    # remove duplicate points
    trk = root.find("g:trk", _GNS)
    for track_segment in trk.findall("g:trkseg", _GNS):
        for point in track_segment.findall("g:trkpt", _GNS):
            time = _get_time(point)
            point_count += 1

            if time in all_timestamps:
                removed_point_count += 1
                track_segment.remove(point)
                continue

            all_timestamps.add(time)

        # check whether at least one point remains in segment
        if not track_segment.findall("g:trkpt", _GNS):
            # remove empty segment
            trk.remove(track_segment)

    # sanity check
    if point_count - len(all_timestamps) != removed_point_count:
        raise Exception("Removed point count does not match, please report to script author. ")

    print(
        f"Filtered {removed_point_count} points from {point_count} "
        f"and {len(all_timestamps)} points remaining"
    )
    _write_gpx(output_file_name, tree)


class Point:
    def __init__(self, node: ET):
        self.node = node
        self.ele = _get_elevation(node)
        self.time = _get_time(node)
        self.lat = float(node.get("lat"))
        self.lon = float(node.get("lon"))

    def __str__(self):
        return f"{self.time}: {self.ele:10.02f} {self.lat:16.08f} {self.lon:16.08f}"


class Segment:
    def __init__(
        self,
        first: Point,
        last: Point,
    ):
        self.first = first
        self.last = last

        first_point = first.lat, first.lon
        last_point = last.lat, last.lon
        self.distance = gd.geodesic(first_point, last_point, ellipsoid="WGS-84").m


def _smooth_track(
    input_file_name: str,
    output_file_name: str|None=None,
    distance_threshold=_DISTANCE_THRESHOLD,
    smooth_point_count=_SMOOTH_POINT_COUNT,
) -> None:
    """
    Remove too close points
    """
    if output_file_name is None:
        output_file_name = input_file_name

    tree = ET.parse(input_file_name)
    root = tree.getroot()

    point_count = 0
    removed_point_count = 0

    for track_segment in root.iterfind("g:trk/g:trkseg", _GNS):
        last_points = []

        for node_point  in track_segment.findall("g:trkpt", _GNS):
            point_count += 1
            point = Point(node_point)

            # print(f"{point}")

            last_points.append(point)
            # print(f"ADD {point}")

            if len(last_points) < smooth_point_count:
                continue

            # enough points to smooth
            delta = Segment(last_points[0], last_points[-1])
            diff = delta.distance
            # print(f"DISTANCE {diff:10.03f}")
            if diff < distance_threshold:
                assert len(last_points) > 2, "Not enough points"
                # remove entire segment except one point
                for p in last_points[1:-1]:
                    track_segment.remove(p.node)
                    removed_point_count += 1
                    # print(f"REMOVE {p.time}")

                last_points = [last_points[0], last_points[-1]]
                # print(f"{last_points[0]} LEFT")
                continue

            # shift script
            last_points = last_points[1:]
            # print(f"SHIFT to {last_points[0]}")
            # last_points.append(point)  # bug was here

    remaining_point_count = point_count - removed_point_count
    print(
        f"Smoothed {removed_point_count} points, "
        f"{remaining_point_count} remains at {smooth_point_count}"
    )

    _write_gpx(output_file_name, tree)


def _exit(message):
    print(message)
    sys.exit(1)


def main():
    """
    GPX Tools Entry Point
    """
    ET.register_namespace("g", _NS)
    ET.register_namespace("", _NS)

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-i", "--input",
        help="Input file names (comma-separated)",
        required=False,
        default=None,
    )
    parser.add_argument(
        "-o", "--output",
        help="Output track name",
        required=False,
        default="_output.gpx",
    )
    parser.add_argument(
        "-c", "--smooth-point-count",
        help="Smooth point count",
        required=False,
        default=str(_SMOOTH_POINT_COUNT),
    )
    parser.add_argument(
        "-d", "--distance-threshold",
        help="Smooth distance threshold",
        required=False,
        default=str(_DISTANCE_THRESHOLD)
    )
    parser.add_argument(
        "-n", "--dry-run",
        help="Dry run: do not write anything, just calc some stats",
        required=False,
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "-s", "--smooth",
        help="Apply smoothing to output track",
        required=False,
        default=False,
        action="store_true",
    )

    args = parser.parse_args()
    output_file_name = args.output

    smooth_point_count = None
    distance_threshold = None

    if args.smooth:
        if args.smooth_point_count:
            try:
                smooth_point_count = int(args.smooth_point_count)
            except Exception as e:
                print(f"Smooth point count must be integer value: {e}")
                sys.exit(1)

        if args.distance_threshold:
            try:
                distance_threshold = int(args.distance_threshold)
            except Exception as e:
                print(f"Distance threshold must be integer value: {e}")
                sys.exit(1)

    if not args.dry_run:
        Path(output_file_name).unlink(missing_ok=True)

    track_file_names = []
    if args.input:
        if not os.path.exists(args.input):
            _exit(f"File {args.input} does not exist")
        track_file_names = [args.input]
    else:
        track_file_names = _get_track_list(output_file_name)

    print("Source files:")
    for track in track_file_names:
        print(f"  Source: {track}")

    # copy first track "as is"
    shutil.copy(track_file_names[0], output_file_name)

    if len(track_file_names) > 1:
        # merge all other tracks into it
        for track_name in track_file_names[1:]:
            _merge_tracks(
                left_file_name=output_file_name,
                right_file_name=track_name,
            )

    _filter_duplicates(output_file_name)

    if args.smooth:
        _smooth_track(
            input_file_name=output_file_name,
            smooth_point_count=smooth_point_count,
            distance_threshold=distance_threshold,
        )


if __name__ == "__main__":
    main()
