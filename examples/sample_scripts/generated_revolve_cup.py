# -*- coding: utf-8 -*-
"""直筒茶杯(空心)建模脚本。"""
import rhinoscriptsyntax as rs

H = 90.0
outer_r = 45.0
inner_r = 42.5

def main():
    rs.AddLayer("茶杯", (150, 90, 60))
    outer = rs.AddCylinder((0, 0, 0), H, outer_r, cap=True)
    inner = rs.AddCylinder((0, 0, 2.5), H - 2.5, inner_r, cap=True)
    cup = rs.BooleanDifference([outer], [inner], delete_input=True)
    if cup:
        rs.ObjectLayer(cup[0], "茶杯")
        rs.ObjectName(cup[0], "直筒茶杯")
        print("茶杯 is_solid OK, 壁厚=%.2fmm" % 2.5)
        __result__ = {"cup_guid": str(cup[0]), "note": "壁厚%.2fmm" % 2.5}
        import json as _json
        print("__GOLEM_RESULT__" + _json.dumps(__result__))
    else:
        __result__ = {"error": "布尔差失败"}

try:
    main()
except Exception as e:
    import traceback; traceback.print_exc()
    __result__ = {"error": str(e)}
