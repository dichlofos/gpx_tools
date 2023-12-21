#!/usr/bin/env python3

import typing as tp
import tqdm
import shutil
from pathlib import Path

import glob
import tqdm
import os
import sys
import argparse

from xml import etree
from xml.etree import ElementTree as ET
from geopy import distance as gd


_DISTANCE_THRESHOLD = 10

_NS = "http://www.topografix.com/GPX/1/1"
_GNS = {"g": _NS}


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
    return sorted(file_name for file_name in glob.glob(glob_path) if Path(file_name).resolve() != output_path)


def _merge_tracks(left_file_name: str, right_file_name: str, output_file_name: tp.Optional[str]=None) -> None:
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
        for trkseg in right_segments:
            main_trk.append(trkseg)
            print("  Added segment to main track")
            added_segments += 1
        print(f"Merged {added_segments} segments")
    else:
        print("No track info found")

    added_waypoints = 0
    for wpt in right_root.iterfind("g:wpt", _GNS):
        added_waypoints += 1
        left_root.append(wpt)

    print(f"Merged {added_waypoints} waypoints")

    ET.indent(left_tree, space="    ")
    left_tree.write(output_file_name, encoding="UTF-8")


def _filter_duplicates(input_file_name: str, output_file_name: str=None) -> None:
    """
    Remove duplicated points from track
    """
    if output_file_name is None:
        output_file_name = input_file_name

    tree = ET.parse(input_file_name)
    root = tree.getroot()

    all_timestamps = set()

    point_count = 0
    removed_point_count = 0
    # remove duplicate points
    for track_segment in root.iterfind("g:trk/g:trkseg", _GNS):
        for point in track_segment.findall("g:trkpt", _GNS):
            time = _get_time(point)
            point_count += 1
            if time in all_timestamps:
                removed_point_count += 1
                track_segment.remove(point)
                continue

            all_timestamps.add(time)

    print(len(all_timestamps), point_count, removed_point_count)
    # sanity check
    if point_count - len(all_timestamps) != removed_point_count:
        raise Exception("Removed point count does not match, please report to script author. ")

    print(f"Filtered {removed_point_count} points from {point_count} and {len(all_timestamps)} points remaining")

    ET.indent(tree, space="    ")
    tree.write(output_file_name, encoding="UTF-8")


def main():
    ET.register_namespace("g", _NS)
    ET.register_namespace("", _NS)

    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", help="Output track name", required=False, default="_output.gpx")
    parser.add_argument("-n", "--dry-run", help="Dry run: do not write anything, just calc some stats", required=False, default=False)

    args = parser.parse_args()
    output_file_name = args.output

    if not args.dry_run:
        Path(output_file_name).unlink(missing_ok=True)

    track_file_names = _get_track_list(output_file_name)
    print("Source files:")
    for track in track_file_names:
        print(f"  Source: {track}")

    if len(track_file_names) > 2:
        # copy first track "as is"
        shutil.copy(track_file_names[0], output_file_name)
        # merge all other tracks into it
        for track_name in track_file_names[1:]:
            _merge_tracks(
                left_file_name=output_file_name,
                right_file_name=track_name,
            )

    _filter_duplicates(output_file_name)

    sys.exit(1)

    if not os.path.exists(input_file_name):
        print(f"Error: File `{input_file_name}` not found")
        sys.exit(2)

    tree = ET.parse(input_file_name)
    root = tree.getroot()


    # track_segment - родительские элементы для точек разделённых участков трека
    # т.е. перебираем все ветви <trkseg>...</trkseg>

    ns = {"g": _NS}
    point_count = 0
    # remove duplicate points
    for track_segment in tqdm.tqdm(root.iterfind("g:trk/g:trkseg", ns)):
        for point in track_segment.findall("g:trkpt", ns):
            time = _get_time(point)
            # print(time)
            point_count += 1
            if time in all_times:
                assert False
                track_segment.remove(point)
                # print("removed")
                continue

            all_times.add(time)

    print(f"Enumerated {len(all_times)} unique points from {point_count}")

    for track_segment in tqdm.tqdm(root.iterfind("g:trk/g:trkseg", ns)):

        # Найдём lat, lon и ele (если есть, иначе 0) первой точки участка
        prev_point = track_segment.find("g:trkpt", ns)
        latitude_prev = prev_point.get("lat")
        longitude_prev = prev_point.get("lon")

        elevation_prev = _get_elevation(prev_point)

        # Удалим из дерева элементов все точки, расстояние между которыми
        # меньше 20м. Исключение - перепад высоты больше 1м
        first = True
        for point in track_segment.findall("g:trkpt", ns):
            if first:
                # пропускаем первую точку
                first = False
                continue

            latitude = point.get("lat")
            longitude = point.get("lon")
            elevation = _get_elevation(point)

            elevation_delta = abs(elevation - elevation_prev)
            if elevation_delta > 1:
                elevation_prev = elevation
                continue

            # Считаем расстояние между точками
            mark1 = latitude_prev, longitude_prev
            mark2 = latitude, longitude
            distance = gd.geodesic(mark1, mark2, ellipsoid="WGS-84").m

            if distance < _DISTANCE_THRESHOLD:
                # print("removed point")
                # track_segment.remove(point)
                pass
            else:
                latitude_prev = latitude
                longitude_prev = longitude
                elevation_prev = elevation

    # Записываем новый xml-документ на основе полученного дерева
    tree.write(output_file_name, encoding="UTF-8")


if __name__ == "__main__":
    main()
