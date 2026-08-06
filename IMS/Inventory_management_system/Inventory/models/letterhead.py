import logging

from django.core.validators import FileExtensionValidator
from django.db import models
import auto_prefetch

logger = logging.getLogger(__name__)

# A4 at 72 dpi, the unit WeasyPrint and PyMuPDF both work in.
A4_WIDTH_PT = 595
A4_HEIGHT_PT = 842
PT_PER_MM = 2.834645669


class Letterhead(auto_prefetch.Model):
    """
    The Ministry letterhead applied to generated release memos and letters.

    **Scope: the release letter to MMU, first page only.** Continuation pages
    print on plain paper, so the letterhead is stamped on page 1 and pages 2+
    get `cont_inset_top` instead of the (much larger) calibrated top inset.

    The approval memo is an internal document printed on a plain sheet — no
    letterhead, no seal, no org header — so it carries its own `memo_inset_*`
    margins and is never stamped at all.

    The active row is resolved at render time (`Letterhead.current()`). An
    officer uploads a scan of the printed letterhead — **PDF, PNG or JPEG** —
    and calibrates the printable area so body text clears the header and footer
    bands. Mirrors HTMS's `letterhead_path` + `letterhead_insets`.

    Insets are stored in **points** (1/72"), the unit both WeasyPrint's `@page`
    rule and PyMuPDF work in, so the number an officer drags to on screen is
    the number the renderer uses. A4 is 595 x 842 pt.

    Modes:
      * a file is uploaded            -> it is stamped underneath every page of
        the generated document and the body is inset clear of it;
      * `pre_printed=True`            -> nothing is drawn; the insets simply
        reserve space on the Ministry's pre-printed paper;
      * no file, not pre-printed      -> a plain text header is built from the
        org_* fields, so documents are never header-less.

    A PDF letterhead is stamped as vector (crisp at any zoom, small files); a
    PNG/JPEG is stamped as the raster it is. Either way `preview_image` holds a
    rasterised page 1 for the calibration screen, which needs something the
    browser can display.
    """

    name = models.CharField(
        max_length=120, default='Ministry Letterhead',
        help_text="Label for this letterhead configuration (admin only).",
    )
    file = models.FileField(
        upload_to='letterhead/', blank=True, null=True,
        validators=[FileExtensionValidator(['pdf', 'png', 'jpg', 'jpeg'])],
        help_text="Scan of the printed letterhead - full A4 page, PDF/PNG/JPEG.",
    )
    # Rasterised page 1, generated on save. Used by the calibration screen and
    # the on-screen document preview; the PDF pipeline uses `file` directly so a
    # PDF letterhead stays vector.
    preview_image = models.ImageField(
        upload_to='letterhead/preview/', blank=True, null=True, editable=False,
        help_text="Auto-generated raster preview of page 1.",
    )
    pre_printed = models.BooleanField(
        default=False,
        help_text="Printing on pre-printed Ministry paper: draw nothing, just reserve the insets.",
    )

    # -- Release letter: printable area INSIDE the letterhead, in points. -----
    inset_top = models.PositiveSmallIntegerField(
        default=184, help_text="Points from the top edge - where the letterhead header ends.")
    inset_bottom = models.PositiveSmallIntegerField(
        default=106, help_text="Points from the bottom edge - where the footer begins.")
    inset_left = models.PositiveSmallIntegerField(default=73, help_text="Points from the left edge.")
    inset_right = models.PositiveSmallIntegerField(default=62, help_text="Points from the right edge.")
    # Page 2 onwards prints on PLAIN paper — there is no header band to clear,
    # so only the top margin differs. Left/right/bottom stay as calibrated so
    # the text block lines up with page 1.
    cont_inset_top = models.PositiveSmallIntegerField(
        default=62,
        help_text="Top margin in points for continuation pages (page 2 onwards, plain paper).")

    # -- Approval memo: plain sheet, so it needs its own margins. -------------
    # The memo is an internal document printed on blank paper; it never carries
    # the letterhead, and inheriting the letterhead's insets would leave it with
    # a ~65mm top margin sized to clear artwork that isn't there.
    memo_inset_top = models.PositiveSmallIntegerField(
        default=62, help_text="Approval memo top margin in points (plain sheet).")
    memo_inset_bottom = models.PositiveSmallIntegerField(
        default=62, help_text="Approval memo bottom margin in points.")
    memo_inset_left = models.PositiveSmallIntegerField(
        default=62, help_text="Approval memo left margin in points.")
    memo_inset_right = models.PositiveSmallIntegerField(
        default=62, help_text="Approval memo right margin in points.")

    # Text fallback header (used only when no file and not pre-printed).
    org_name = models.CharField(
        max_length=200, default='Ministry of Energy and Green Transition', blank=True)
    org_address = models.CharField(max_length=300, blank=True, default='P.O. Box SD 40, Accra')
    org_contact = models.CharField(max_length=300, blank=True, default='')

    active = models.BooleanField(default=True, help_text="Only the most recently updated active row is used.")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-updated_at']
        verbose_name = 'letterhead'
        verbose_name_plural = 'letterheads'

    def __str__(self):
        return self.name

    # -- Resolution ----------------------------------------------------------
    @classmethod
    def current(cls):
        """The active letterhead to render on, or None (documents use a bare header)."""
        return cls.objects.filter(active=True).order_by('-updated_at').first()

    @property
    def is_pdf(self):
        return bool(self.file and self.file.name.lower().endswith('.pdf'))

    @property
    def insets_pt(self):
        """Printable area of the release letter, inside the letterhead."""
        return {'top': self.inset_top, 'right': self.inset_right,
                'bottom': self.inset_bottom, 'left': self.inset_left}

    @property
    def memo_insets_pt(self):
        """Margins of the approval memo, which prints on a plain sheet."""
        return {'top': self.memo_inset_top, 'right': self.memo_inset_right,
                'bottom': self.memo_inset_bottom, 'left': self.memo_inset_left}

    # -- Preview rasterisation -----------------------------------------------
    def build_preview(self, dpi=110, save=True):
        """Rasterise page 1 of `file` into `preview_image`.

        The calibration screen and the HTML document preview both need
        something an <img> can show, and a PDF is not that. 110 dpi puts an A4
        page at roughly 900x1270 - sharp enough to position guide lines against,
        small enough to inline as a data-URI without bloating the page.

        Never raises: a letterhead that cannot be rasterised still stamps onto
        the PDF correctly, it just loses its on-screen preview.
        """
        if not self.file:
            return False

        if not self.is_pdf:
            # Already an image - reuse the upload itself as the preview.
            if self.preview_image.name != self.file.name:
                self.preview_image.name = self.file.name
                if save and self.pk:
                    super().save(update_fields=['preview_image'])
            return True

        try:
            self.file.open('rb')
            data = self.file.read()
            self.file.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Letterhead %s: could not read file: %s", self.pk, exc)
            return False

        try:
            import fitz  # PyMuPDF - already a hard dependency (scan validation)
            from django.core.files.base import ContentFile

            doc = fitz.open(stream=data, filetype='pdf')
            if not doc.page_count:
                doc.close()
                return False
            pix = doc.load_page(0).get_pixmap(dpi=dpi)
            png = pix.tobytes('png')
            doc.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Letterhead %s: PDF rasterisation failed: %s", self.pk, exc)
            return False

        base = (self.file.name.rsplit('/', 1)[-1].rsplit('.', 1)[0] or 'letterhead')
        self.preview_image.save(f"{base}_p1.png", ContentFile(png), save=False)
        if save and self.pk:
            super().save(update_fields=['preview_image'])
        return True

    def save(self, *args, **kwargs):
        """Persist, then (re)build the preview whenever the source file changes."""
        # A save that is only writing preview_image must not recurse.
        update_fields = kwargs.get('update_fields') or []
        if 'preview_image' in update_fields:
            return super().save(*args, **kwargs)

        previous_file = None
        if self.pk:
            previous_file = (Letterhead.objects.filter(pk=self.pk)
                             .values_list('file', flat=True).first())

        super().save(*args, **kwargs)

        if self.file and (self.file.name != previous_file or not self.preview_image):
            self.build_preview()
