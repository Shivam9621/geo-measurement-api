import zipfile
from pathlib import Path

import pyproj
import shapefile
from shapely.geometry import Polygon


def generate_sample_kml(output_path: Path) -> None:
    """Generate sample.kml with polygon, linestring, and point around Bengaluru."""
    kml_text = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Bengaluru Survey Sample</name>
    <description>Demonstration features in EPSG:4326 around Bengaluru</description>
    <Placemark>
      <name>Plot A</name>
      <description>Commercial Development Parcel</description>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.6000,12.9700,0
              77.6000,12.9800,0
              77.5900,12.9800,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Road 1</name>
      <description>Outer Ring Road Link</description>
      <LineString>
        <coordinates>
          77.5900,12.9700,0
          77.6100,12.9900,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Gate</name>
      <description>Security Access Point</description>
      <Point>
        <coordinates>
          77.6000,12.9800,0
        </coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(kml_text.strip(), encoding="utf-8")
    print(f"Created: {output_path}")


def generate_sample_shapefile_zip(output_path: Path) -> None:
    """Generate sample_shapefile.zip containing shapefile in EPSG:4326."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stem = "sample_parcels"
    temp_dir = output_path.parent / "_temp_shp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    shp_base = temp_dir / stem
    w = shapefile.Writer(str(shp_base))
    w.field("name", "C", size=50)
    w.field("category", "C", size=30)
    w.field("est_val", "N", decimal=2)

    # Polygon 1
    poly1 = Polygon(
        [(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98), (77.59, 12.97)]
    )
    w.poly([list(poly1.exterior.coords)])
    w.record("Cubbon Park Zone", "Recreational", 1500000.0)

    # Polygon 2 (smaller parcel)
    poly2 = Polygon(
        [(77.61, 12.97), (77.62, 12.97), (77.62, 12.98), (77.61, 12.98), (77.61, 12.97)]
    )
    w.poly([list(poly2.exterior.coords)])
    w.record("Tech Park Phase 1", "Commercial", 3400000.0)

    w.close()

    # Projection file
    prj_path = temp_dir / f"{stem}.prj"
    prj_path.write_text(pyproj.CRS.from_epsg(4326).to_wkt(), encoding="utf-8")

    # Zip files together
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in (".shp", ".shx", ".dbf", ".prj"):
            file_to_pack = temp_dir / f"{stem}{ext}"
            zf.write(file_to_pack, arcname=f"{stem}{ext}")

    # Clean up temporary shapefile files
    for item in temp_dir.iterdir():
        item.unlink(missing_ok=True)
    temp_dir.rmdir()

    print(f"Created: {output_path}")


def main() -> None:
    sample_dir = Path(__file__).resolve().parent.parent / "sample_data"
    kml_file = sample_dir / "sample.kml"
    zip_file = sample_dir / "sample_shapefile.zip"

    generate_sample_kml(kml_file)
    generate_sample_shapefile_zip(zip_file)
    print("Sample data generation finished.")


if __name__ == "__main__":
    main()
