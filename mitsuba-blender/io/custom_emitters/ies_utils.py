import numpy as np

def parse_data_from_line(f_handle, num_val_to_read):
	num_phis_read = 0
	# read_new_line = True
	vert_angles = []
	while(num_phis_read < num_val_to_read):
		
		line = f_handle.readline()
		strings = line.split()

		for num in strings:
			vert_angles.append(float(num))
			num_phis_read += 1

	return vert_angles

def read_ies_data(fn):
	ies_data = None
	# try different methods to load the file
	try:
		ies_data = read_ies_data_osram(fn)
		return ies_data
	except:
		print("Failed to load IES file using OSRAM method")
	
	try:
		ies_data = read_ies_data_format1(fn)
		return ies_data
	except:
		print("Failed to load IES file using IES library method")

	return ies_data

# it seems that files from ies library has the same format
# read IESNA91 format
# read LM-63-2002 format
def read_ies_data_format1(fn):
	with open(fn, 'r') as f:
		# get the ies format
		line = f.readline()
		format = line.split(":")[1]
		print(f"IES format: {format}")
		# if format != "IESNA91" or format != "LM-63-2002":
		# 	print("IES format not supported")
		# 	return None
		# ignore till TILT
		TILT_found = False
		TILT_type = None
		while not TILT_found:
			line = f.readline()
			if line.startswith("TILT"):
				TILT_found = True
				TILT_type = line.split("=")[1]

		# ignore next 4 lines
		if TILT_type == "INCLUDE":
			for _ in range(4):
				f.readline()

		# <#lamps> <lumensperlamp> <candela multiplier> <#verts> <#horis>
		# get number of vert angles
		line = f.readline()
		num_phis = int(line.split()[3])
		num_thetas = int(line.split()[4])

		# ignore the actual phi and theta vals
		parse_data_from_line(f, num_phis)
		parse_data_from_line(f, num_thetas)

		ies_data = np.zeros((num_phis, num_thetas), np.float32)

		# each line contains data for a single hori angle
		for i in range(num_thetas):
			ies_data[:,i] = np.array(parse_data_from_line(f, num_phis))

	return ies_data

def read_ies_data_osram(fn):
	with open(fn, 'r') as f:
		# get the ies format
		line = f.readline()
		format = line.split(":")[1]
		print(f"IES format: {format}")
		if format != "LM-63-2002":
			print("IES format not supported")
			return None
		# ignore next 9 lines
		for _ in range(9):
			line = f.readline()

		# get number of vert angles
		line = f.readline()
		num_phis = int(line)
		# get number of hori angles
		line = f.readline()
		num_thetas = int(line)

		# ignore next 4 lines
		for _ in range(4):
			f.readline()

		# ignore the actual phi and theta vals
		parse_data_from_line(f, num_phis)
		parse_data_from_line(f, num_thetas)

		ies_data = np.zeros((num_phis, num_thetas), np.float32)

		# each line contains data for a single hori angle
		for i in range(num_thetas):
			ies_data[:,i] = np.array(parse_data_from_line(f, num_phis))

	return ies_data


# def convert_ies_to_image(fn, outfn):
# 	from skimage.io import imsave
# 	ies_data = read_ies_data(fn)
# 	# plt.imshow(ies_data)
# 	# plt.show()
# 	imsave(outfn, ies_data)

# if __name__ == '__main__':
# 	import sys

# 	fn = sys.argv[1]
# 	print(fn)
# 	convert_ies_to_image(fn, fn.replace(".ies", ".exr"))
