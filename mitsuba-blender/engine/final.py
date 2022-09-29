import bpy
import tempfile
import os
import numpy as np
from ..io.exporter import SceneConverter


class MitsubaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "MITSUBA"
    bl_label = "Mitsuba"
    bl_use_preview = False

    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self):
        self.scene_data = None
        self.draw_data = None
        self.converter = SceneConverter(render=True)

    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        pass

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        from mitsuba import set_variant
        b_scene = depsgraph.scene
        set_variant(b_scene.mitsuba.variant)
        # need to call only setting a variant
        from . import custom_integrators
        custom_integrators.register()
        # ---
        from mitsuba import ScopedSetThreadEnvironment, Thread
        with ScopedSetThreadEnvironment(b_scene.thread_env):
            scale = b_scene.render.resolution_percentage / 100.0
            self.size_x = int(b_scene.render.resolution_x * scale)
            self.size_y = int(b_scene.render.resolution_y * scale)

            # Temporary workaround as long as the dict creation writes stuff to dict
            # with tempfile.TemporaryDirectory() as dummy_dir:
            dummy_dir = "/home/arpit/Downloads/blender_tmp_dir/"
            filepath = os.path.join(dummy_dir, "scene.xml")
            self.converter.set_path(filepath)
            self.converter.scene_to_dict(depsgraph)
            global curr_thread
            curr_thread = Thread.thread()
            curr_thread.file_resolver().prepend(dummy_dir)
            mts_scene = self.converter.dict_to_scene()

            sensor = mts_scene.sensors()[0]
            mts_scene.integrator().render(mts_scene, sensor)
            render_results = sensor.film().bitmap().split()
            bmp = sensor.film().bitmap()
            bmp.write(os.path.join(dummy_dir, "myimg.exr"))

            for result in render_results:
                buf_name = result[0].replace("<root>", "Main")
                channel_count = result[1].channel_count() if result[1].channel_count() != 2 else 3

                # extract name
                res_struct = result[1].struct_()
                result_name = ""
                for ii in range(len(res_struct)):
                    curr_struct_seg = res_struct[ii]
                    result_name += curr_struct_seg.name.split('.')[-1]
                self.add_pass(buf_name, channel_count, result_name)

            blender_result = self.begin_result(0, 0, self.size_x, self.size_y)

            for result in render_results:
                render_pixels = np.array(result[1])
                if result[1].channel_count() == 2:
                    # Add a dummy third channel
                    render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 1))))
                #render_pixels = np.array(render.convert(Bitmap.PixelFormat.RGBA, Struct.Type.Float32, srgb_gamma=False))
                # Here we write the pixel values to the RenderResult
                buf_name = result[0].replace("<root>", "Main")
                layer = blender_result.layers[0].passes[buf_name]
                layer.rect = np.flip(render_pixels, 0).reshape((self.size_x*self.size_y, -1))
            self.end_result(blender_result)
