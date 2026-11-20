//go:build !windows

package apis

import "os"

// isLink reports whether the path, already Lstat'ed into info, is a symlink.
func isLink(path string, info os.FileInfo) bool {
	return info.Mode()&os.ModeSymlink != 0
}
