import bpy
import tempfile
import os
import numpy as np
import array
import gpu
from gpu_extras.presets import draw_texture_2d
from ..io.exporter import SceneConverter

class CustomDrawData:
    def __init__(self, dimensions):
        # Generate dummy float image buffer
        self.dimensions = dimensions
        width, height = dimensions

        pixels = width * height * array.array('f', [0.1, 0.2, 0.1, 1.0])
        pixels = gpu.types.Buffer('FLOAT', width * height * 4, pixels)

        # Generate texture
        self.texture = gpu.types.GPUTexture((width, height), format='RGBA16F', data=pixels)

        # Note: This is just a didactic example.
        # In this case it would be more convenient to fill the texture with:
        # self.texture.clear('FLOAT', value=[0.1, 0.2, 0.1, 1.0])

    def __del__(self):
        del self.texture

    def draw(self):
        draw_texture_2d(self.texture, (0, 0), self.texture.width, self.texture.height)

class MitsubaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "MITSUBA"
    bl_label = "Mitsuba"
    bl_use_preview = True

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

    # For viewport renders, this method gets called once at the start and
    # whenever the scene or 3D viewport changes. This method is where data
    # should be read from Blender in the same thread. Typically a render
    # thread will be started to do the work while keeping Blender responsive.
    def view_update(self, context, depsgraph):
        region = context.region
        view3d = context.space_data
        scene = depsgraph.scene

        # Get viewport dimensions
        dimensions = region.width, region.height

        if not self.scene_data:
            # First time initialization
            self.scene_data = []
            first_time = True

            # Loop over all datablocks used in the scene.
            for datablock in depsgraph.ids:
                pass
        else:
            first_time = False

            # Test which datablocks changed
            for update in depsgraph.updates:
                print("Datablock updated: ", update.id.name)

            # Test if any material was added, removed or changed.
            if depsgraph.id_type_updated('MATERIAL'):
                print("Materials updated")

        # Loop over all object instances in the scene.
        if first_time or depsgraph.id_type_updated('OBJECT'):
            for instance in depsgraph.object_instances:
                pass

    # For viewport renders, this method is called whenever Blender redraws
    # the 3D viewport. The renderer is expected to quickly draw the render
    # with OpenGL, and not perform other expensive work.
    # Blender will draw overlays for selection and editing on top of the
    # rendered image automatically.
    def view_draw(self, context, depsgraph):
        region = context.region
        scene = depsgraph.scene

        # Get viewport dimensions
        dimensions = region.width, region.height

        # Bind shader that converts from scene linear to display space,
        gpu.state.blend_set('ALPHA_PREMULT')
        self.bind_display_space_shader(scene)

        if not self.draw_data or self.draw_data.dimensions != dimensions:
            self.draw_data = CustomDrawData(dimensions)

        self.draw_data.draw()

        self.unbind_display_space_shader()
        gpu.state.blend_set('NONE')

    def render(self, depsgraph):
        if self.is_preview:            
            # self.render_preview(depsgraph)
            pass
        else:
            self.render_final(depsgraph)
    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render_final(self, depsgraph):
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
