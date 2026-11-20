//go:build windows

package apis

import (
	"os"
	"syscall"
)

// isNameSurrogate reports whether a reparse tag marks a link to another named
// entity (a symlink, a junction). Microsoft's rule: bit 29 of the tag. A
// OneDrive cloud placeholder or a deduplicated file has a reparse tag too,
// without that bit, and is an ordinary file to read.
func isNameSurrogate(tag uint32) bool {
	return tag&0x20000000 != 0
}

// isLink reports whether the path, already Lstat'ed into info, is a link that
// must not be followed. Go reports a symlink as ModeSymlink, and since Go 1.23
// a junction, and also a cloud placeholder, as ModeIrregular, so for
// ModeIrregular the reparse tag itself is read. Any error reading it counts
// as a link, so the check fails closed.
func isLink(path string, info os.FileInfo) bool {
	if info.Mode()&os.ModeSymlink != 0 {
		return true
	}
	if info.Mode()&os.ModeIrregular == 0 {
		return false
	}
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return true
	}
	var fd syscall.Win32finddata
	h, err := syscall.FindFirstFile(p, &fd)
	if err != nil {
		return true
	}
	syscall.FindClose(h)
	if fd.FileAttributes&syscall.FILE_ATTRIBUTE_REPARSE_POINT == 0 {
		return false
	}
	return isNameSurrogate(fd.Reserved0)
}
