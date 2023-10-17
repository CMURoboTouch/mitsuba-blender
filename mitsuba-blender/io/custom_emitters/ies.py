import mitsuba as mi
import drjit as dr
from os.path import exists
from .ies_utils import read_ies_data
import mitsuba

mi.set_variant('llvm_ad_rgb')

# dr.set_flag(dr.JitFlag.VCallRecord, False)
# dr.set_flag(dr.JitFlag.LoopRecord, False)

class IES(mi.Emitter):
    def __init__(self, props):
        super().__init__(props)

        # set flags
        self.m_flags = +mi.EmitterFlags.DeltaPosition
        # ---
        self.m_intensity = props.get("intensity", 1.0)
        self.m_ies_fn = props.get("filename","")
        # self.m_ies_scale = props.get("scale", 1.0)

        # load ies profile
        global curr_thread
        curr_thread = mi.Thread.thread()
        fs = curr_thread.file_resolver()
        # logger = curr_thread.logger()
        ies_fn = str(fs.resolve(self.m_ies_fn))
        # TODO: fit an analytic function for importance sampling
        if self.m_ies_fn == "" or (not exists(ies_fn)):
            # raise logger.log(mi.LogLevel.Error, f"IES profile not found - {self.m_ies_fn}")
            print("IES profile not found - {self.m_ies_fn}")
            exit()
        else:
            print(ies_fn)
            ies_profile = read_ies_data(ies_fn)
            self.m_uv_factor = mi.Point2f(ies_profile.shape)
            # convert matrix to bitmap
            ies_tensor = mi.TensorXf(ies_profile.flatten().tolist(), shape=ies_profile.shape + (1,))
            
            self.m_ies_profile = mi.Texture2f(ies_tensor)

    def is_environment(self: mi.Emitter):
        return False
    
    def sampling_weight(self):
        pass

    def flags(self, active):
        return self.flags

    def direction_to_uv(self, local_dir):
        local_dir = dr.normalize(local_dir)
        # calculation theta and phi
        theta = dr.acos(local_dir.z)
        phi = dr.atan2(local_dir.y, local_dir.x)
        # convert to [-1,1]
        theta = theta * dr.rcp(dr.pi)
        phi = phi * dr.rcp(2.0 * dr.pi)

        return mi.Point2f(phi, theta)
    
    def sample_ray(self, time, wv_s, sp_s, dir_s, active):
        # sample direction
        local_dir = mi.warp.square_to_uniform_cone(sp_s, self.m_cos_cutoff_angle)
        pdf_dir = mi.warp.square_to_uniform_cone_pdf(local_dir, self.m_cos_cutoff_angle)

        # sample spec
        si = dr.zeros(mi.SurfaceInteraction3f)
        si.time = time
        si.p = self.world_transform().translation()
        si.uv = self.direction_to_uv(local_dir)
        wavelengths, spec_weight = self.sample_wavelengths(si, wv_s, active)
        uv_coord = self.direction_to_uv(local_dir)
        mul_factor = self.m_ies_profile.eval(uv_coord, active)

        return mi.Ray3f(si.p, self.world_transform() * local_dir, time, wavelengths), \
            (spec_weight * mul_factor / pdf_dir)


    def sample_direction(self, it, sample, active):
        ds = dr.zeros(mi.DirectionSample3f)
        ds.p = self.world_transform().translation()
        ds.n = 0.0
        ds.uv = 0.0
        ds.pdf = 1.0
        ds.time = it.time
        ds.delta = True
        # ds.emitter = None #self
        ds.d = ds.p - it.p
        ds.dist = dr.norm(ds.d)
        inv_dist = dr.rcp(ds.dist)
        ds.d *= inv_dist

        local_d = self.world_transform().inverse() @ -ds.d
        uv_coord = self.direction_to_uv(local_d)
        # the output of the following func is a list
        mul_factor = self.m_ies_profile.eval(uv_coord, active)[0]
        # active &= mul_factor > 0.0

        si = dr.zeros(mi.SurfaceInteraction3f)
        si.t = 0.0
        si.time = it.time
        si.wavelengths = it.wavelengths
        si.p = ds.p 
        radiance = self.m_intensity.eval(si, active)

        return ds, (radiance & active ) * (mul_factor * dr.sqr(inv_dist))

    def pdf_direction(self, it, dir_s, active):
        return 0.0

    def eval_direction(self, it, ds, active):
        pass

    def sample_position(self, time, sample, active):
        center_dir = self.world_transform() * mi.ScalarVector3f(0.0, 0.0, 1.0)
        ps = mi.PositionSample3f(
            self.world_transform().translation(), center_dir,
            mi.Point2f(0.5), time, 1.0, True
        )   

        return ps, mi.Float(1.0)

    def sample_wavelength(self, si, sample, active):
        # TODO: sample_shifted will not work
        wav, weight = self.m_intensity.sample_spectrum(si, 
                mi.math.sample_shifted(sample), active)
        
        return wav, weight

    def eval(self, si, mask):
        return 0.0
    
    def bbox(self):
        p = self.world_transform().scalar() * mi.ScalarPoint3f(0.0)
        return mi.BoundingBox3f(p, p)
    



