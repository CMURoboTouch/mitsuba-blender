import bpy
import tempfile
import os
import numpy as np
import threading
import sys
from ..io.exporter import SceneConverter

from ipdb import set_trace
import traceback

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

    def render1(self, depsgraph):
        scene = depsgraph.scene
        scale = scene.render.resolution_percentage / 100.0
        self.size_x = int(scene.render.resolution_x * scale)
        self.size_y = int(scene.render.resolution_y * scale)

        # Fill the render result with a flat color. The framebuffer is
        # defined as a list of pixels, each pixel itself being a list of
        # R,G,B,A values.
        if self.is_preview:
            color = [0.1, 0.2, 0.1, 1.0]
        else:
            color = [0.2, 0.1, 0.1, 1.0]

        pixel_count = self.size_x * self.size_y
        rect = [color] * pixel_count

        # Here we write the pixel values to the RenderResult
        result = self.begin_result(0, 0, self.size_x, self.size_y)
        layer = result.layers[0].passes["Combined"]
        layer.rect = rect
        self.end_result(result)

        from mitsuba import set_variant
        b_scene = depsgraph.scene
        set_variant(b_scene.mitsuba.variant)
        # need to call only setting a variant
        from . import custom_integrators
        custom_integrators.register()
        # ---
        import mitsuba as mi
        from mitsuba import ScopedSetThreadEnvironment, Thread
        with ScopedSetThreadEnvironment(b_scene.thread_env):
            ar = mi.Thread.thread()
            mi.set_log_level(mi.LogLevel.Trace)

        br = mi.Thread.thread()
        new_logger = mi.Logger(mi.LogLevel.Trace)
        br.set_logger(new_logger)
        mi.set_log_level(mi.LogLevel.Trace)
        print("End of func")

        set_trace()

        # # Here we write the pixel values to the RenderResult
        # result = self.begin_result(0, 0, self.size_x, self.size_y)
        # layer = result.layers[0].passes["Combined"]
        # layer.rect = rect
        # self.end_result(result)


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
        import mitsuba as mi
        from mitsuba import ScopedSetThreadEnvironment, Thread

        # if Thread.thread().logger() is None:
        #     main_logger = mi.Logger(mi.LogLevel.Trace)
        #     main_thread = Thread.thread()
        #     set_trace()
        #     main_thread.set_logger(main_logger)

        # get current thread
        main_thread = Thread.thread()
        # main_id = main_thread.thread_id()
        main_parent = main_thread.parent()
        print(str(main_thread), main_parent)

        print(f"ref count: main thread - {sys.getrefcount(main_thread)}, scene env thread - {sys.getrefcount(b_scene.thread_env)}")

        print(f"Before start thread_id - {threading.get_ident()}/{threading.active_count()}")
        try:
            with ScopedSetThreadEnvironment(b_scene.thread_env):
                print(f"Inside scoped env thread_id - {threading.get_ident()}/{threading.active_count()}")
                scale = b_scene.render.resolution_percentage / 100.0
                self.size_x = int(b_scene.render.resolution_x * scale)
                self.size_y = int(b_scene.render.resolution_y * scale)

                print("dumping scene")
                # Temporary workaround as long as the dict creation writes stuff to dict
                # with tempfile.TemporaryDirectory() as dummy_dir:
                # with "/home/arpit/Downloads/blender_tmp_dir/" as dummy_dir:
                dummy_dir = "/home/arpit/Downloads/blender_tmp_dir/"
                filepath = os.path.join(dummy_dir, "scene.xml")
                self.converter.set_path(filepath)
                self.converter.scene_to_dict(depsgraph)

                global curr_thread
                
                curr_thread = Thread.thread()
                curr_thread.file_resolver().prepend(dummy_dir)
                # curr_id = curr_thread.thread_id()
                curr_parent = curr_thread.parent()
                print(str(curr_thread), curr_parent)

                print(f"ref count: main thread - {sys.getrefcount(main_thread)}, scene env thread - {sys.getrefcount(b_scene.thread_env)}")

                # Thread.thread().file_resolver().prepend(dummy_dir)
                print("Loading scene in mitsuba to render")
                mts_scene = self.converter.dict_to_scene()

                sensor = mts_scene.sensors()[0]
                print("Rendering step")
                mts_scene.integrator().render(mts_scene, sensor)
                bmp = sensor.film().bitmap()
                bmp.write("myimg.exr")
                render_results = sensor.film().bitmap().split()

                print("Feeding to blender GUI")
                for result in render_results:
                    print(result)
                    buf_name = result[0].replace("<root>", "Main")
                    channel_count = result[1].channel_count() if result[1].channel_count() != 2 else 3
                    # self.add_pass(buf_name, channel_count, ''.join([f.name.split('.')[-1] for f in result[1].struct_()]))
                    self.add_pass(buf_name, channel_count, "RGB")
                    print("ADDED Pass")

                print("begin result")
                blender_result = self.begin_result(0, 0, self.size_x, self.size_y)

                print("STAGE 2")

                for result in render_results:
                    render_pixels = np.array(result[1])
                    print(render_pixels.shape)
                    if result[1].channel_count() == 2:
                        # Add a dummy third channel
                        render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 1))))
                    #render_pixels = np.array(render.convert(Bitmap.PixelFormat.RGBA, Struct.Type.Float32, srgb_gamma=False))
                    # Here we write the pixel values to the RenderResult
                    buf_name = result[0].replace("<root>", "Main")
                    layer = blender_result.layers[0].passes[buf_name]
                    layer.rect = np.flip(render_pixels, 0).reshape((self.size_x*self.size_y, -1))
                print("STAGE 3")
                self.end_result(blender_result)
                print("end result")

        except Exception:
            print('Failed to initialize mitsuba-blender add-on with exception:')
            traceback.print_exc()

        print(f"Outside scoped env thread_id - {threading.get_ident()}/{threading.active_count()}")
        print(f"ref count: main thread - {sys.getrefcount(main_thread)}, scene env thread - {sys.getrefcount(b_scene.thread_env)}")
        print("--------")
        main_thread = Thread.thread()
        # main_id = main_thread.thread_id()
        main_parent = main_thread.parent()
        print(str(main_thread), main_parent)
        print(f"ref count: main thread - {sys.getrefcount(main_thread)}, scene env thread - {sys.getrefcount(b_scene.thread_env)}")
        
        # print(f"thread count - {Thread.thread_count()}")
        print(dir())
        print("End of func")


        # set_trace()
