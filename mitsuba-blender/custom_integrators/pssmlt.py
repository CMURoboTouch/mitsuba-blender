import drjit as dr
import mitsuba as mi
from mitsuba import SamplingIntegrator

def get_class(name):
    names = name.split("_") 
    name = "drjit." + ".".join(names[:-1])

    name = name.split('.')
    value = __import__(".".join(name[:-1]))
    for item in name[1:]:
        value = getattr(value, item)
    dr.set_flag(dr.JitFlag.LoopRecord, True)

    return value


def mis_weight(pdf_a, pdf_b):
    pdf_a *= pdf_a
    pdf_b *= pdf_b
    return dr.select(pdf_a > 0.0, pdf_a / (pdf_a + pdf_b), mi.Float(0.0))

class MyPathIntegrator(SamplingIntegrator):
    def __init__(self, props):
        SamplingIntegrator.__init__(self, props)
        self.max_depth = props.get("max_depth", 5)
        self.rr_depth = props.get("rr_depth", 5)
        self.hide_emitters = props.get("hide_emitters", False)

    def sample(self, scene, sampler, rays, medium, active):
        
        p = get_class(mi.variant())
        # loop state
        ray = mi.Ray3f(rays)
        throughput = mi.Spectrum(1)
        result = mi.Spectrum(0)
        eta = mi.Float(1)
        depth = mi.UInt32(0)
        # hide emitters
        valid_ray = mi.Mask(not self.hide_emitters & dr.neq(scene.environment(), None))
        
        # previous bounce
        prev_si = dr.zeros(mi.SurfaceInteraction3f)
        prev_bsdf_pdf = mi.Float(1)
        prev_bsdf_delta = mi.Bool(True)
        ctx = mi.BSDFContext()
        # ------
        # loop ctx
        loop = p.Loop("Path Tracer", lambda: (
                    sampler, ray, throughput, result,
                    eta, depth, valid_ray, prev_si, prev_bsdf_pdf, 
                    prev_bsdf_delta, active
            ))
        loop.set_max_iterations(self.max_depth)
        
        while loop(active):


            si = scene.ray_intersect(ray)
            active = si.is_valid() & active
            # Visible emitters
            emitter_vis = si.emitter(scene, active)
            
            # following is not available for jitted code
            # if dr.any(dr.neq(emitter_vis, None)):
            if True:
            
                ds = mi.DirectionSample3f(scene, si, prev_si)
                em_pdf = mi.Float(0.)

                # if dr.any(~prev_bsdf_delta):
                if True:
                    em_pdf = scene.pdf_emitter_direction(prev_si, ds,
                        ~prev_bsdf_delta)
                mis_bsdf = mis_weight(prev_bsdf_pdf, em_pdf)
                
                result = dr.fma(
                    throughput, 
                    ds.emitter.eval(si, prev_bsdf_pdf > 0.) * mis_bsdf,
                    result
                    )
            
            
            # continue tracing
            active_next = (depth+1 < self.max_depth) & si.is_valid()

            # following statement is not available in jit mode
            # if dr.none_or<False>(active_next):
            if False:
                break

            bsdf = si.bsdf(rays)

            # Emitter sampling
            sample_emitter = active_next & mi.has_flag(bsdf.flags(), mi.BSDFFlags.Smooth)
            # if dr.any(sample_emitter):
            if True:
                ds, emitter_val = scene.sample_emitter_direction(
                    si, sampler.next_2d(sample_emitter), 
                    True, sample_emitter)
                active_e = sample_emitter & dr.neq(ds.pdf, 0.0)
                
                wo = si.to_local(ds.d)
                bsdf_val, bsdf_pdf = \
                        bsdf.eval_pdf(ctx, si, wo, active_e)
                bsdf_val = si.to_world_mueller(bsdf_val, -wo, si.wi)
            
                mis_em = dr.select(ds.delta, mi.Float(1), mis_weight(ds.pdf, bsdf_pdf))
                result[active_e] = dr.fma(
                            throughput, 
                            emitter_val * bsdf_val * mis_em, 
                            result)

            # BSDF sampling
            active_b = active
            bs, bsdf_val = bsdf.sample(ctx, si, 
                sampler.next_1d(active), 
                sampler.next_2d(active), 
                active_b
            )
            bsdf_val = si.to_world_mueller(bsdf_val, -bs.wo, si.wi)
            
            ray = si.spawn_ray(si.to_world(bs.wo))
                        
            # update loop vars
            throughput *= bsdf_val
            eta *= bs.eta
            valid_ray |= active & si.is_valid() & ~mi.has_flag(bs.sampled_type, mi.BSDFFlags.Null)

            # info current vertex
            prev_si = si
            prev_bsdf_pdf = bs.pdf
            prev_bsdf_delta = mi.has_flag(bs.sampled_type, mi.BSDFFlags.Delta)
            # stopping criterion
            depth[si.is_valid()] += 1
            throughput_max = dr.max(throughput)

            rr_prob = dr.minimum(throughput_max * dr.sqr(eta), 0.95)
            rr_active = (depth >= self.rr_depth)
            rr_continue = sampler.next_1d() < rr_prob
            # rr
            throughput[rr_active] *= dr.rcp(dr.detach(rr_prob))
            active = active_next & (~rr_active | rr_continue) & \
                dr.neq(throughput_max, 0.)
            # 

        return result, si.is_valid(), [dr.select(si.is_valid(), si.t, mi.Float(0.0))]

    def aov_names(self):
        return ["depth.Y"]

    def to_string(self):
        return "MyPathIntegrator[]"