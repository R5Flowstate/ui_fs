"""Convert an RSX ui JSON export into a Repak .ruip. ui_fs.dll must export a function named after the asset."""

import json
import os
import struct
import sys

RUIP_MAGIC = 0x50495552
PACKAGE_VERSION = 2

HDR_FMT = ("<IHHQ" "ffff" "HHHHHHHHHHH" "2x" "IIII" "QQQQQQQQQQQ")
HDR_V1_SIZE = struct.calcsize(HDR_FMT)   # 160
HDR_V2_SIZE = HDR_V1_SIZE + 12
ARGUMENT_SIZE = 8
ARG_CLUSTER_SIZE = 18
STYLE_V39_SIZE = 68


def build(js):
    hexes = {k: bytes.fromhex(js.get(k, "") or "") for k in (
        "defaultValuesHex", "defaultStringsHex", "transformDataHex",
        "argClustersHex", "styleDescriptorsHex", "renderJobsHex",
        "keyframingsHex", "argNamesHex")}

    name = js["name"].encode() + b"\0"

    args = bytearray()
    for a in sorted(js["args"], key=lambda a: a["index"]):
        args += struct.pack("<BBHHH", a["type"], a["unk_1"], a["dataOffset"],
                            a["nameOffset"], int(a["shortHash"], 16))

    if len(args) != js["argCount"] * ARGUMENT_SIZE:
        raise SystemExit("argCount %d does not match %d packed args"
                         % (js["argCount"], len(args) // ARGUMENT_SIZE))
    if len(hexes["styleDescriptorsHex"]) != js["styleDescriptorCount"] * STYLE_V39_SIZE:
        raise SystemExit("styleDescriptors are %d bytes, expected %d x 68"
                         % (len(hexes["styleDescriptorsHex"]), js["styleDescriptorCount"]))
    if len(hexes["argClustersHex"]) != js["argClusterCount"] * ARG_CLUSTER_SIZE:
        raise SystemExit("argClusters are %d bytes, expected %d x 18"
                         % (len(hexes["argClustersHex"]), js["argClusterCount"]))

    body = bytearray()
    off = {}

    def put(key, blob):
        off[key] = HDR_V2_SIZE + len(body)
        body.extend(blob)

    put("name", name)
    put("argCluster", hexes["argClustersHex"])
    put("arguments", args)
    put("styleDescriptor", hexes["styleDescriptorsHex"])
    put("renderJob", hexes["renderJobsHex"])
    put("transformData", hexes["transformDataHex"])
    put("defaultValues", hexes["defaultValuesHex"])
    put("defaultStringData", hexes["defaultStringsHex"])
    put("keyframing", hexes["keyframingsHex"])
    put("argNames", hexes["argNamesHex"])
    put("rpakPtr", b"")

    # RSX's pointerFixups all target the asset header, and Repak rebuilds every
    # header pointer itself. Only CPU-blob-internal fixups (string pointers
    # inside defaultValues) would need forwarding, and this asset has none.
    fixups = [f for f in js.get("pointerFixups", [])
              if f.get("srcSection") != "header"]
    put("pointerFixup", b"".join(
        struct.pack("<IIII", 1, f["srcOffset"], 1, f["dstCpuOffset"]) for f in fixups))

    hdr = struct.pack(
        HDR_FMT,
        RUIP_MAGIC, PACKAGE_VERSION, js["version"], off["name"],
        js["elementWidth"], js["elementHeight"],
        js["elementWidthRatio"], js["elementHeightRatio"],
        js["defaultValuesSize"], js["ruiDataStructSize"],
        js["styleDescriptorCount"], js["unk_A4"], js["renderJobCount"],
        js["argClusterCount"], js["argCount"], js["keyframingCount"],
        js["transformDataSize"], len(name), 0,
        len(hexes["argNamesHex"]), len(hexes["renderJobsHex"]),
        len(hexes["keyframingsHex"]), len(hexes["defaultStringsHex"]),
        off["argNames"], off["argCluster"], off["arguments"],
        off["styleDescriptor"], off["renderJob"], off["keyframing"],
        off["transformData"], off["defaultValues"], off["defaultStringData"],
        off["rpakPtr"], len(hexes["defaultStringsHex"]))
    hdr += struct.pack("<IQ", len(fixups), off["pointerFixup"])

    if js["transformDataSize"] != len(hexes["transformDataHex"]):
        raise SystemExit("transformDataSize %d but blob is %d bytes"
                         % (js["transformDataSize"], len(hexes["transformDataHex"])))
    if js["defaultValuesSize"] != len(hexes["defaultValuesHex"]):
        raise SystemExit("defaultValuesSize %d but blob is %d bytes"
                         % (js["defaultValuesSize"], len(hexes["defaultValuesHex"])))

    return bytes(hdr) + bytes(body)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    js = json.load(open(sys.argv[1], encoding="utf-8"))
    blob = build(js)
    os.makedirs(os.path.dirname(os.path.abspath(sys.argv[2])), exist_ok=True)
    open(sys.argv[2], "wb").write(blob)
    print("%s -> %s  (%d bytes, ruiVersion %d, %d widgets, %d args, %d styles)"
          % (js["name"], sys.argv[2], len(blob), js["version"],
             js["renderJobCount"], js["argCount"], js["styleDescriptorCount"]))


if __name__ == "__main__":
    main()
