"""Photo try-on: 'tryon' image type, tryon_img in the API, the slim
/api/products/tryon list, and the import_tryon_images command."""
import io
import shutil
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from Product.models import ProductImage, ProductInfo, ProductInstance
from Product.serializer import ProductInstanceSerializer


def png_bytes(alpha=True, size=(40, 20)):
    mode = 'RGBA' if alpha else 'RGB'
    im = Image.new(mode, size, (10, 10, 10, 0) if alpha else (245, 245, 245))
    if alpha:
        for x in range(size[0]):
            im.putpixel((x, 0), (10, 10, 10, 255))
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()


def make_product(model='1085', frame_width=138):
    return ProductInfo.objects.create(
        model_number=model, name=f'Frame {model}', price='49.00',
        letter_size='M', string_size='54-16-145', frame_weight=20,
        frame_width=frame_width, lens_width=54, bridge=16, temple_length=145,
        lens_height=40, upper_wearable_width=0, lower_wearable_width=0,
        nose_pad='Standard', frame_style='Full-Rim')


def make_instance(product, sku, colour='Black', online=True):
    return ProductInstance.objects.create(
        product=product, sku=sku, slug=sku.lower(), color_base_name='black',
        color_display_name=colour, online=online, stock=5)


def add_image(inst, image_type, name='x.png', alpha=True):
    img = ProductImage(productInstance=inst, image_type=image_type, alt='a')
    img.image.save(name, ContentFile(png_bytes(alpha)), save=True)
    return img


class MediaTempMixin:
    def setUp(self):
        super().setUp()
        self._media = tempfile.mkdtemp()
        self._override = override_settings(MEDIA_ROOT=self._media)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self._media, ignore_errors=True)
        super().tearDown()


class TryOnSerializerTests(MediaTempMixin, TestCase):
    def test_choice_exists(self):
        choices = dict(ProductImage._meta.get_field('image_type').choices)
        self.assertEqual(choices['tryon'], 'Try-on')

    def test_tryon_img_none_without_image(self):
        inst = make_instance(make_product(), '1085-BLK-001')
        add_image(inst, 'carousel')
        data = ProductInstanceSerializer(inst).data
        self.assertIsNone(data['tryon_img'])
        self.assertEqual(len(data['carousel_img']), 1)

    def test_tryon_img_is_first_upload_and_not_in_carousel(self):
        inst = make_instance(make_product(), '1085-BLK-001')
        add_image(inst, 'carousel', 'c.png')
        first = add_image(inst, 'tryon', 'first.png')
        add_image(inst, 'tryon', 'second.png')
        data = ProductInstanceSerializer(inst).data
        self.assertTrue(data['tryon_img'].endswith(first.image.url))
        self.assertEqual(len(data['carousel_img']), 1)
        self.assertNotIn(data['tryon_img'], data['carousel_img'])

    def test_model_endpoint_returns_tryon_per_colour(self):
        product = make_product()
        black = make_instance(product, '1085-BLK-001', 'Black')
        make_instance(product, '1085-CLR-002', 'Clear')
        add_image(black, 'tryon')
        res = APIClient().get('/api/products/1085/')
        self.assertEqual(res.status_code, 200)
        by_sku = {i['sku']: i for i in res.data['productInstance']}
        self.assertIsNotNone(by_sku['1085-BLK-001']['tryon_img'])
        self.assertIsNone(by_sku['1085-CLR-002']['tryon_img'])


class TryOnFramesEndpointTests(MediaTempMixin, TestCase):
    def test_lists_only_online_colours_with_tryon(self):
        a = make_product('1085', 138)
        a_black = make_instance(a, '1085-BLK-001', 'Black')
        make_instance(a, '1085-CLR-002', 'Clear')                  # no tryon
        a_off = make_instance(a, '1085-TOR-003', 'Tortoise', online=False)
        add_image(a_black, 'tryon', 'cutout.png')
        add_image(a_black, 'carousel', 'front.png')
        add_image(a_off, 'tryon')
        b = make_product('1439', 136)
        add_image(make_instance(b, '1439-RED-001', 'Red'), 'carousel')  # none
        c = make_product('1450', 131)
        add_image(make_instance(c, '1450-BLK-001', 'Black', online=False), 'tryon')

        res = APIClient().get('/api/products/tryon')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([p['model_number'] for p in res.data], ['1085'])
        frame = res.data[0]
        self.assertEqual(frame['frame_width'], 138)
        self.assertEqual([c['sku'] for c in frame['colors']], ['1085-BLK-001'])
        self.assertIsNotNone(frame['colors'][0]['thumbnail'])
        self.assertIn('cutout', frame['colors'][0]['tryon_img'])
        self.assertIn('front', frame['colors'][0]['thumbnail'])


class ImportTryOnCommandTests(MediaTempMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.src = Path(tempfile.mkdtemp())
        self.product = make_product('1085')
        self.black = make_instance(self.product, '1085-BLK-001', 'Black')
        self.clear = make_instance(self.product, '1085-CLR-002', 'Clear')
        self.tort = make_instance(self.product, '1085-TOR-003', 'Tortoise & Gold')

    def tearDown(self):
        shutil.rmtree(self.src, ignore_errors=True)
        super().tearDown()

    def write(self, rel, alpha=True):
        path = self.src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_bytes(alpha))
        return path

    def run_cmd(self, *args):
        out, err = io.StringIO(), io.StringIO()
        call_command('import_tryon_images', str(self.src), *args,
                     stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def tryon_count(self, inst):
        return inst.productImage.filter(image_type='tryon').count()

    def test_imports_by_sku_and_by_model_colour(self):
        self.write('1085-blk-001.png')                 # SKU, any case
        self.write('1085/tortoise-and-gold.png')       # model/colour
        self.write('nothing-like-this.png')
        out, err = self.run_cmd()
        self.assertEqual(self.tryon_count(self.black), 1)
        self.assertEqual(self.tryon_count(self.tort), 1)
        self.assertEqual(self.tryon_count(self.clear), 0)
        self.assertIn('UNMATCHED', err)
        self.assertIn('added 2', out)
        self.assertIn('1085-CLR-002', out)  # listed as still missing
        img = self.black.productImage.get(image_type='tryon')
        self.assertTrue(img.image.name.startswith('product_images/tryon_1085-BLK-001'))

    def test_dry_run_writes_nothing(self):
        self.write('1085-BLK-001.png')
        out, _ = self.run_cmd('--dry-run')
        self.assertIn('would add', out)
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_rerun_skips_and_replace_swaps(self):
        self.write('1085-BLK-001.png')
        self.run_cmd()
        old = self.black.productImage.get(image_type='tryon')
        tryon_dir = Path(old.image.path).parent
        out, _ = self.run_cmd()
        self.assertIn('skipped 1', out)
        self.assertEqual(self.tryon_count(self.black), 1)
        out, _ = self.run_cmd('--replace')
        self.assertIn('replaced 1', out)
        new = self.black.productImage.get(image_type='tryon')
        self.assertNotEqual(old.pk, new.pk)
        # the old file is gone: exactly one stored try-on file for the SKU
        self.assertEqual(len(list(tryon_dir.glob('tryon_1085-BLK-001*'))), 1)
        self.assertTrue(Path(new.image.path).exists())

    def test_refuses_opaque_and_broken_images(self):
        self.write('1085-BLK-001.png', alpha=False)
        (self.src / '1085-CLR-002.png').write_bytes(b'not an image')
        out, err = self.run_cmd()
        self.assertIn('REFUSED (no transparency)', err)
        self.assertIn('REFUSED (cannot open', err)
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_replace_keeps_other_image_types(self):
        add_image(self.black, 'carousel')
        add_image(self.black, 'tryon')
        self.write('1085-BLK-001.png')
        self.run_cmd('--replace')
        self.assertEqual(self.black.productImage.filter(image_type='carousel').count(), 1)
        self.assertEqual(self.tryon_count(self.black), 1)

    def test_two_files_for_one_colour_is_an_error(self):
        self.write('1085-BLK-001.png')
        self.write('1085/black.png')
        with self.assertRaises(CommandError):
            self.run_cmd()
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_missing_directory(self):
        with self.assertRaises(CommandError):
            call_command('import_tryon_images', '/no/such/dir')
