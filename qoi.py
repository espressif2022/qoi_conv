import numpy as np
from PIL import Image

# encoder/decoder for lossloss image file format: https://qoiformat.org/
# ./test_images also from https://qoiformat.org/

class Pixel:
    def __init__(self, r, g, b, a) -> 'Pixel':
        self.r = r
        self.g = g
        self.b = b
        self.a = a

    def __repr__(self) -> str:
        return f"({self.r}, {self.g}, {self.b}, {self.a})"

    def __eq__(self, other) -> bool:
        return self.r == other.r and self.g == other.g and self.b == other.b and self.a == other.a

    def decode_diff(self, decode_value) -> 'Pixel':
        r = (self.r + (((decode_value >> 4) & 0b11) - 2)) % 256
        g = (self.g + (((decode_value >> 2) & 0b11) - 2)) % 256 
        b = (self.b + (( decode_value       & 0b11) - 2)) % 256
        return Pixel(r, g, b, self.a)
    
    def decode_diff_luma(self, dg, byte) -> 'Pixel':
        nr = byte >> 4
        nb = byte & 0b1111
        ng = dg - 32
        g = (self.g + ng         ) % 256
        r = (self.r + ng - 8 + nr) % 256
        b = (self.b + ng - 8 + nb) % 256
        return Pixel(r, g, b, self.a)

    def hash(self) -> int:
        return ((self.r * 3 + self.g * 5 + self.b * 7 + self.a * 11) % 64)

class Qoi:
    QOI_OP_RGB  = 0b11111110 # 254
    QOI_OP_RGBA = 0b11111111 # 255

    QOI_OP_INDEX = 0b00 # 0
    QOI_OP_DIFF  = 0b01 # 1
    QOI_OP_LUMA  = 0b10 # 2
    QOI_OP_RUN   = 0b11 # 3

    def load(self, file_name) -> 'Qoi':
        self.header = { "name": file_name }
        self.file = open(file_name, "rb")

        header = bytearray(self.file.read(14))
        if header[0:4] != b'qoif': return None

        self.header["head"      ] = b'qoif'
        self.header["width"     ] = header[4] * 16**6 + header[5] * 16**4 + header[6]  * 16**2 + header[7]
        self.header["height"    ] = header[8] * 16**6 + header[9] * 16**4 + header[10] * 16**2 + header[11]
        self.header["channels"  ] = header[12]
        self.header["colorspace"] = header[13]

        self.image = []
        self.__decode()
        return self

    def save(self, file_name, data) -> 'Qoi':
        height, width, channels = data.shape
        self.image = data
        self.file = open(file_name, "wb")
        self.header = { "name": file_name }
        self.header["head"      ] = b'qoif'
        self.header["width"     ] = width
        self.header["height"    ] = height
        self.header["channels"  ] = channels
        self.header["colorspace"] = 0

        self.__write_header()
        self.__encode()
        self.file.close()
        return self

    def __repr__(self) -> str:
        return str(self.header)

    def height(self) -> int:
        return self.header["height"]

    def width(self) -> int:
        return self.header["width"]

    def channels(self) -> int:
        return self.header["channels"]

    def image(self) -> list:
        return self.image

    def image_data(self) -> np.array:
        if self.channels() == 3:
            data = [np.array([np.uint8(x.r), np.uint8(x.g), np.uint8(x.b)]) for x in self.image]
        elif self.channels() == 4:
            data = [np.array([np.uint8(x.r), np.uint8(x.g), np.uint8(x.b), np.uint8(x.a)]) for x in self.image]

        array = np.array(data).reshape(self.height(), self.width(), self.channels())
        return array

    def __write_header(self) -> None:
        self.file.write(bytearray(self.header["head"]))
        self.file.write(self.__convert_int(self.header["width" ]))
        self.file.write(self.__convert_int(self.header["height"]))
        self.file.write(self.header["channels"  ].to_bytes(1, byteorder = 'little'))
        self.file.write(self.header["colorspace"].to_bytes(1, byteorder = 'little'))

    def __write_run(self, run) -> None:
        frame = bytearray(1)
        frame[0] = (self.QOI_OP_RUN << 6) + run - 1
        self.file.write(frame)

    def __write_rgba(self, r, g, b, a) -> None:
        frame = bytearray([self.QOI_OP_RGBA, r, g, b, a])
        self.file.write(frame)

    def __write_rgb(self, r, g, b) -> None:
        frame = bytearray([self.QOI_OP_RGB, r, g, b])
        self.file.write(frame)

    def __encode(self) -> None:
        array = [Pixel(0, 0, 0, 0) for _ in range(64)]
        pixel = Pixel(0, 0, 0, 255) # start value of pixel

        channels = self.header["channels"]
        if channels != 3 and channels != 4: return

        run = 0
        cases = { 'run': 0, 'lookup': 0, 'diff': 0, 'diff2': 0, 'full1': 0, 'full2': 0 }

        for i in range(self.height()):
            for j in range(self.width()):
                if channels == 3:
                    pixel_new = Pixel(self.image[i,j,0], self.image[i,j,1], self.image[i,j,2], pixel.a)
                else:
                    pixel_new = Pixel(self.image[i,j,0], self.image[i,j,1], self.image[i,j,2], self.image[i,j,3])

                # sequential pixels
                if pixel == pixel_new and run < 62:
                    cases['run'] += 1
                    run += 1
                    continue

                # close previous run
                if run > 0:
                    self.__write_run(run)
                    run = 0

                # lookup current pixel
                if array[pixel_new.hash()] == pixel_new:
                    cases['lookup'] += 1
                    frame = bytearray(1)
                    frame[0] = pixel_new.hash()
                    self.file.write(frame)
                    pixel = pixel_new
                    continue

                if pixel.a != pixel_new.a:
                    cases['full2'] += 1
                    self.__write_rgba(pixel_new.r, pixel_new.g, pixel_new.b, pixel_new.a)
                    array[pixel_new.hash()] = pixel_new
                    pixel = pixel_new
                    continue
                
                dr = np.intc(pixel_new.r) - np.intc(pixel.r)
                dg = np.intc(pixel_new.g) - np.intc(pixel.g)
                db = np.intc(pixel_new.b) - np.intc(pixel.b)
                if dr >  128: dr -= 256
                if dg >  128: dg -= 256
                if db >  128: db -= 256
                if dr < -127: dr += 256
                if dg < -127: dg += 256
                if db < -127: db += 256
                dg_r = dr - dg
                dg_b = db - dg
                if dg_r >  128: dg_r -= 256
                if dg_b >  128: dg_b -= 256
                if dg_r < -127: dg_r += 256
                if dg_b < -127: dg_b += 256
              
                # print(f'{i}/{j}: {(dr + 2) << 4 | (dg + 2) << 2 | (db + 2)} | {dr},{dg},{db} | {dg_r}, {dg_b} | {pixel} -> {pixel_new}')

                # small diff
                if all(-3 < x < 2 for x in (dr, dg, db)):
                    cases['diff'] += 1                    
                    frame = bytearray([self.QOI_OP_DIFF << 6 | (dr + 2) << 4 | (dg + 2) << 2 | (db + 2)])
                    self.file.write(frame)
                    array[pixel_new.hash()] = pixel_new
                    pixel = pixel_new       
                    continue

                # medium diff
                elif all(-9 < x < 8 for x in (dg_r, dg_b)) and -33 < dg < 32:
                    cases['diff2'] += 1                    
                    frame = bytearray(2)
                    frame[0] = self.QOI_OP_LUMA << 6 | (dg + 32)
                    frame[1] = (dg_r + 8) << 4 | (dg_b + 8)
                    self.file.write(frame)
                    array[pixel_new.hash()] = pixel_new
                    pixel = pixel_new       
                    continue

                # write full pixel data
                cases['full1'] += 1
                self.__write_rgb(pixel_new.r, pixel_new.g, pixel_new.b)
                array[pixel_new.hash()] = pixel_new
                pixel = pixel_new
                
        # close open runs
        if run > 1: self.__write_run(run)
        # write end marker
        print(f'{cases} / {sum(cases.values())}')
        self.file.write(bytearray(8))

    def __convert_int(self, number) -> bytearray:
        bytes = bytearray(4)
        for i in range(4):
            bytes[3-i] = number % 256
            number = number >> 8
        return bytes

    def __read_byte(self) -> int:
        byte = self.file.read(1)
        if byte == b'':
            return None
        else:
            return int.from_bytes(byte, 'little')
       
    def __read_bytes(self, count) -> list:
        return [ self.__read_byte() for _ in range(count)]

    def __decode(self) -> None:
        image_size = self.width() * self.height() * self.channels()
        decoded_image = []

        cases = { 'run': 0, 'lookup': 0, 'diff': 0, 'diff2': 0, 'full1': 0, 'full2': 0 }

        array = [Pixel(0, 0, 0, 0) for _ in range(64)]
        pixel = Pixel(0, 0, 0, 255) # start value of pixel

        for i in range(image_size):
            value = self.__read_byte()
            if value is None: break

            if value == self.QOI_OP_RGB:
                cases['full1'] += 1
                r, g, b = self.__read_bytes(3)
                pixel = Pixel(r, g, b, pixel.a)
                array[pixel.hash()] = pixel
                decoded_image.append(pixel)
            elif value == self.QOI_OP_RGBA:
                cases['full2'] += 1
                r, g, b, a = self.__read_bytes(4)
                pixel = Pixel(r, g, b, a)
                array[pixel.hash()] = pixel
                decoded_image.append(pixel)
            else:
                decode_type = value // 64
                decode_value = value % 64
                if decode_type == self.QOI_OP_INDEX:
                    cases['lookup'] += 1
                    pixel = array[decode_value]
                    decoded_image.append(pixel)
                elif decode_type == self.QOI_OP_DIFF:
                    cases['diff'] += 1
                    pixel = pixel.decode_diff(decode_value)
                    array[pixel.hash()] = pixel
                    decoded_image.append(pixel)
                elif decode_type == self.QOI_OP_LUMA:
                    cases['diff2'] += 1
                    next_byte = self.__read_byte()
                    pixel = pixel.decode_diff_luma(decode_value, next_byte)
                    array[pixel.hash()] = pixel
                    decoded_image.append(pixel)
                elif decode_type == self.QOI_OP_RUN:
                    cases['run'] += decode_value + 1
                    [decoded_image.append(pixel) for _ in range(decode_value + 1)]

        print(f'{cases} / {sum(cases.values())}')
        self.image = decoded_image[0:-8] # discard 8 end marker


print("load:")
image = Qoi().load("./test_images/qoi_logo.qoi")
data = image.image_data()
print("save:")
Qoi().save('test.qoi', data)

print("load_again:")
image2 = Qoi().load("test.qoi")
i = Image.fromarray(image2.image_data())
i.save("test.png")
